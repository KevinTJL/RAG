export const API_URL = import.meta.env.VITE_API_URL || '';

const tokenKey = 'local_rag_auth_token';
const userKey = 'local_rag_auth_user';

export type AuthUser = { id: string; email: string };

export function getAuthToken() {
  return localStorage.getItem(tokenKey) || '';
}

export function getAuthUser(): AuthUser | null {
  const raw = localStorage.getItem(userKey);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    localStorage.removeItem(userKey);
    return null;
  }
}

export function setAuthSession(token: string, user: AuthUser) {
  localStorage.setItem(tokenKey, token);
  localStorage.setItem(userKey, JSON.stringify(user));
}

export function clearAuthSession() {
  localStorage.removeItem(tokenKey);
  localStorage.removeItem(userKey);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers || {});
  const token = getAuthToken();
  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  const res = await fetch(`${API_URL}${path}`, { ...init, headers });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || data.message || '请求失败');
  return data;
}

export function getUserId() {
  return getAuthUser()?.id || '';
}

export type KnowledgeScope = 'system' | 'personal';
export type SearchScope = 'all' | 'personal' | 'system';
export type SelectedFile = { scope: KnowledgeScope; source: string };

export type UserSettings = {
  top_k: number;
  deepseek_thinking_enabled: boolean;
  deepseek_thinking: Record<string, boolean>;
  search_scope: SearchScope;
  selected_files: SelectedFile[];
  custom_openai: {
    base_url: string;
    model_name: string;
    temperature?: number | null;
    top_p?: number | null;
    max_tokens?: number | null;
    timeout?: number | null;
    enabled_for_chat: boolean;
    enabled_for_review: boolean;
    has_api_key: boolean;
  };
};

export const api = {
  register: (body: { email: string; password: string }) =>
    request<{ token: string; user: AuthUser }>('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  login: (body: { email: string; password: string }) =>
    request<{ token: string; user: AuthUser }>('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  me: () => request<{ user: AuthUser }>('/api/auth/me'),
  models: () => request<{ default_chat_model: string; chat_models: string[]; embed_model: string }>('/api/models'),
  settings: () => request<{ settings: UserSettings }>('/api/settings'),
  updateSettings: (body: any) =>
    request<{ settings: UserSettings }>('/api/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  testOpenAISettings: () => request<{ message: string; preview: string }>('/api/settings/test-openai', { method: 'POST' }),
  files: () => request<{ files: string[]; personal_files: string[]; system_files: string[]; data_dir?: string; system_data_dir?: string }>('/api/files'),
  upload: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return request<{ message: string }>('/api/upload', { method: 'POST', body: form });
  },
  ingest: () => request<{ message: string }>('/api/ingest', { method: 'POST' }),
  deleteFile: (filename: string) => request<{ message: string }>(`/api/files/${encodeURIComponent(filename)}`, { method: 'DELETE' }),
  previewFile: (filename: string, scope: KnowledgeScope = 'personal') =>
    request<any>(`/api/files/${encodeURIComponent(filename)}/preview?scope=${encodeURIComponent(scope)}`),
  rawFileUrl: (filename: string, scope: KnowledgeScope = 'personal') =>
    `${API_URL}/api/files/${encodeURIComponent(filename)}/raw?scope=${encodeURIComponent(scope)}&access_token=${encodeURIComponent(getAuthToken())}`,
  profile: (userId: string) => request<{ profile: any }>(`/api/profile/${encodeURIComponent(userId)}`),
  deleteProfileTag: (userId: string, body: { category: string; value: string }) =>
    request<{ profile: any }>(`/api/profile/${encodeURIComponent(userId)}/tag/delete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  clearHistory: (userId: string) => request<{ profile: any; message: string }>(`/api/user/${encodeURIComponent(userId)}/history`, { method: 'DELETE' }),
  clearAllHistory: (userId: string) => request<{ profile: any; message: string }>(`/api/user/${encodeURIComponent(userId)}/all-history`, { method: 'DELETE' }),
  query: (body: any) => request<any>('/api/query', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  reviewHistory: (userId: string) => request<{ sessions: any[] }>(`/api/review/history/${encodeURIComponent(userId)}`),
  createReviewPlan: (body: any) => request<{ session: any }>('/api/review/plan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  answerReview: (body: any) => request<any>('/api/review/answer', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  completeReview: (body: any) => request<any>('/api/review/complete', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  deleteReviewSession: (userId: string, sessionId: string) =>
    request<{ message: string; sessions: any[] }>(`/api/review/${encodeURIComponent(userId)}/${encodeURIComponent(sessionId)}`, { method: 'DELETE' }),
  deleteReviewStep: (userId: string, sessionId: string, stepId: string) =>
    request<{ message: string; session: any }>(
      `/api/review/${encodeURIComponent(userId)}/${encodeURIComponent(sessionId)}/steps/${encodeURIComponent(stepId)}`,
      { method: 'DELETE' },
    ),
};
