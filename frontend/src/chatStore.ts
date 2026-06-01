import { computed, ref } from 'vue';
import { api, getUserId } from './api';
import { settingsStore } from './settingsStore';

type ChatRole = 'user' | 'bot';

export type ChatMessage = {
  role: ChatRole;
  content: string;
  requestId?: string;
  chunks?: any[];
  followups?: string[];
  learningInsight?: any;
};

export type Conversation = {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messages: ChatMessage[];
  selectedChatModel: string;
  answering: boolean;
  pendingRequestId?: string;
};

const userId = getUserId();
const legacyMessagesKey = `local_rag_messages_${userId}`;
const conversationsKey = `local_rag_conversations_${userId}`;
const activeConversationKey = `local_rag_active_conversation_${userId}`;
const profileCacheKey = `local_rag_profile_${userId}`;
const selectedChatModelKey = 'local_rag_selected_chat_model';
const builtInChatModels = ['qwen2.5:3b', 'deepseek-v4-pro', 'deepseek-v4-flash'];

const conversations = ref<Conversation[]>(loadConversations());
const activeConversationId = ref(localStorage.getItem(activeConversationKey) || conversations.value[0]?.id || '');
const profile = ref<any>(null);
const profileLoading = ref(false);
const profileError = ref('');
const profileCachedAt = ref(0);
const chatModels = ref<string[]>([...builtInChatModels]);
const selectedChatModel = ref(localStorage.getItem(selectedChatModelKey) || conversations.value[0]?.selectedChatModel || 'qwen2.5:3b');

if (!activeConversationId.value) {
  activeConversationId.value = createConversation('新的对话');
}
ensureActiveConversation();

const activeConversation = computed(() => {
  ensureActiveConversation();
  return conversations.value.find((conversation) => conversation.id === activeConversationId.value) || conversations.value[0];
});
const messages = computed(() => activeConversation.value?.messages || []);
const answering = computed(() => Boolean(activeConversation.value?.answering));
const anyConversationAnswering = computed(() => conversations.value.some((conversation) => conversation.answering));
const activeAnswerCount = computed(() => conversations.value.filter((conversation) => conversation.answering).length);

function uid() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function now() {
  return Date.now();
}

function defaultConversation(title = '新的对话', messages: ChatMessage[] = []): Conversation {
  const timestamp = now();
  return {
    id: uid(),
    title,
    createdAt: timestamp,
    updatedAt: timestamp,
    messages,
    selectedChatModel: localStorage.getItem(selectedChatModelKey) || 'qwen2.5:3b',
    answering: false,
  };
}

function safeParse<T>(raw: string | null, fallback: T): T {
  if (!raw) return fallback;
  try {
    return JSON.parse(raw);
  } catch {
    return fallback;
  }
}

function normalizeConversation(value: any): Conversation | null {
  if (!value || typeof value !== 'object') return null;
  const messages = Array.isArray(value.messages) ? value.messages : [];
  return {
    id: String(value.id || uid()),
    title: String(value.title || inferTitle(messages) || '新的对话'),
    createdAt: Number(value.createdAt || now()),
    updatedAt: Number(value.updatedAt || now()),
    messages,
    selectedChatModel: String(value.selectedChatModel || localStorage.getItem(selectedChatModelKey) || 'qwen2.5:3b'),
    answering: false,
    pendingRequestId: '',
  };
}

function loadConversations() {
  const stored = safeParse<any[]>(localStorage.getItem(conversationsKey), []);
  const loaded = stored.map(normalizeConversation).filter(Boolean) as Conversation[];
  if (loaded.length) return loaded.sort((a, b) => b.updatedAt - a.updatedAt);

  const legacyMessages = safeParse<ChatMessage[]>(localStorage.getItem(legacyMessagesKey), []);
  if (legacyMessages.length) {
    const migrated = defaultConversation('历史对话', legacyMessages);
    localStorage.removeItem(legacyMessagesKey);
    localStorage.setItem(conversationsKey, JSON.stringify([migrated]));
    localStorage.setItem(activeConversationKey, migrated.id);
    return [migrated];
  }

  const initial = defaultConversation('新的对话');
  localStorage.setItem(conversationsKey, JSON.stringify([initial]));
  localStorage.setItem(activeConversationKey, initial.id);
  return [initial];
}

function saveConversations() {
  localStorage.setItem(conversationsKey, JSON.stringify(conversations.value));
  localStorage.setItem(activeConversationKey, activeConversationId.value);
}

function ensureActiveConversation() {
  if (conversations.value.some((conversation) => conversation.id === activeConversationId.value)) return;
  activeConversationId.value = conversations.value[0]?.id || createConversation('新的对话');
  saveConversations();
}

function inferTitle(items: ChatMessage[]) {
  const firstQuestion = items.find((message) => message.role === 'user')?.content || '';
  return firstQuestion.trim().slice(0, 24);
}

function touchConversation(conversation: Conversation) {
  conversation.updatedAt = now();
  if (!conversation.title || conversation.title === '新的对话') {
    conversation.title = inferTitle(conversation.messages) || conversation.title || '新的对话';
  }
}

function createConversation(title = '新的对话') {
  const conversation = defaultConversation(title);
  conversations.value = [conversation, ...conversations.value];
  activeConversationId.value = conversation.id;
  selectedChatModel.value = conversation.selectedChatModel;
  saveConversations();
  return conversation.id;
}

function selectConversation(id: string) {
  const conversation = conversations.value.find((item) => item.id === id);
  if (!conversation) return;
  activeConversationId.value = id;
  selectedChatModel.value = conversation.selectedChatModel;
  localStorage.setItem(selectedChatModelKey, selectedChatModel.value);
  saveConversations();
}

function renameConversation(id: string, title: string) {
  const conversation = conversations.value.find((item) => item.id === id);
  if (!conversation) return;
  conversation.title = title.trim() || '未命名对话';
  touchConversation(conversation);
  saveConversations();
}

function deleteConversation(id: string) {
  if (conversations.value.length <= 1) {
    const only = conversations.value[0];
    only.messages = [];
    only.title = '新的对话';
    only.updatedAt = now();
    only.answering = false;
    only.pendingRequestId = '';
    activeConversationId.value = only.id;
    saveConversations();
    return;
  }
  conversations.value = conversations.value.filter((conversation) => conversation.id !== id);
  if (activeConversationId.value === id) {
    activeConversationId.value = conversations.value[0].id;
    selectedChatModel.value = conversations.value[0].selectedChatModel;
  }
  saveConversations();
}

function apiRole(role: string) {
  return role === 'bot' ? 'assistant' : role;
}

function saveProfileCache(nextProfile: any) {
  if (!nextProfile) return;
  profile.value = nextProfile;
  profileCachedAt.value = Date.now();
  localStorage.setItem(profileCacheKey, JSON.stringify({ profile: nextProfile, cached_at: profileCachedAt.value }));
}

function loadProfileCache() {
  const raw = localStorage.getItem(profileCacheKey);
  if (!raw) return;
  try {
    const data = JSON.parse(raw);
    profile.value = data.profile || null;
    profileCachedAt.value = Number(data.cached_at || 0);
  } catch {
    localStorage.removeItem(profileCacheKey);
  }
}

async function loadProfile() {
  if (!userId) return;
  profileLoading.value = true;
  profileError.value = '';
  try {
    const nextProfile = (await api.profile(userId)).profile;
    saveProfileCache(nextProfile);
  } catch (error: any) {
    profileError.value = error?.message || '画像同步失败';
  } finally {
    profileLoading.value = false;
  }
}

async function loadModels() {
  try {
    const data = await api.models();
    const backendModels = data.chat_models?.length ? data.chat_models : [];
    chatModels.value = Array.from(new Set([...backendModels, ...builtInChatModels]));
    if (!chatModels.value.includes(selectedChatModel.value)) {
      selectedChatModel.value = data.default_chat_model || chatModels.value[0];
      setSelectedChatModel(selectedChatModel.value);
    }
  } catch {
    // Keep the built-in model list when the backend is temporarily unavailable.
  }
}

function setSelectedChatModel(model: string) {
  selectedChatModel.value = model;
  localStorage.setItem(selectedChatModelKey, model);
  const conversation = activeConversation.value;
  if (conversation) {
    conversation.selectedChatModel = model;
    touchConversation(conversation);
    saveConversations();
  }
}

async function sendQuestion(question: string) {
  const conversation = activeConversation.value;
  const trimmed = question.trim();
  if (!conversation || !trimmed || conversation.answering) return;

  const requestId = uid();
  conversation.messages.push({ role: 'user', content: trimmed, requestId });
  conversation.answering = true;
  conversation.pendingRequestId = requestId;
  touchConversation(conversation);
  saveConversations();

  const history = conversation.messages.slice(-5, -1).map(({ role, content }) => ({ role: apiRole(role), content }));
  try {
    const data = await api.query({
      question: trimmed,
      user_id: userId,
      history,
      chat_model: conversation.selectedChatModel || selectedChatModel.value,
      ...settingsStore.chatQueryOptions(),
    });
    conversation.messages.push({
      role: 'bot',
      content: data.answer,
      chunks: data.chunks || [],
      followups: data.followups || [],
      learningInsight: data.learning_insight,
      requestId,
    });
    saveProfileCache(data.profile || profile.value);
  } catch (error: any) {
    conversation.messages.push({
      role: 'bot',
      content: `回答生成失败：${error?.message || '请求失败'}`,
      requestId,
    });
  } finally {
    conversation.answering = false;
    conversation.pendingRequestId = '';
    touchConversation(conversation);
    conversations.value = [...conversations.value].sort((a, b) => b.updatedAt - a.updatedAt);
    saveConversations();
  }
}

async function clearChatHistory() {
  const conversation = activeConversation.value;
  if (!conversation) return;
  conversation.messages = [];
  conversation.title = '新的对话';
  conversation.answering = false;
  conversation.pendingRequestId = '';
  touchConversation(conversation);
  saveConversations();
  await loadProfile();
}

async function clearAllHistory() {
  const data = await api.clearAllHistory(userId);
  const nextConversation = defaultConversation('新的对话');
  conversations.value = [nextConversation];
  activeConversationId.value = nextConversation.id;
  localStorage.removeItem(profileCacheKey);
  profile.value = data.profile || null;
  profileCachedAt.value = 0;
  profileError.value = '';
  saveConversations();
}

async function deleteMessageGroup(index: number) {
  const conversation = activeConversation.value;
  const current = conversation?.messages[index];
  if (!conversation || !current) return;

  if (current.requestId) {
    conversation.messages = conversation.messages.filter((message) => message.requestId !== current.requestId);
  } else {
    const start = current.role === 'bot' && conversation.messages[index - 1]?.role === 'user' ? index - 1 : index;
    const count = conversation.messages[start]?.role === 'user' && conversation.messages[start + 1]?.role === 'bot' ? 2 : 1;
    conversation.messages.splice(start, count);
  }

  touchConversation(conversation);
  saveConversations();
  await loadProfile();
}

async function deleteProfileTag(item: { category: string; value: string }) {
  const nextProfile = (await api.deleteProfileTag(userId, item)).profile;
  saveProfileCache(nextProfile);
}

loadProfileCache();
loadModels();

export const chatStore = {
  userId,
  conversations,
  activeConversationId,
  activeConversation,
  messages,
  answering,
  anyConversationAnswering,
  activeAnswerCount,
  profile,
  profileLoading,
  profileError,
  profileCachedAt,
  chatModels,
  selectedChatModel,
  createConversation,
  selectConversation,
  renameConversation,
  deleteConversation,
  saveProfileCache,
  loadProfileCache,
  loadModels,
  setSelectedChatModel,
  loadProfile,
  sendQuestion,
  clearChatHistory,
  clearAllHistory,
  deleteMessageGroup,
  deleteProfileTag,
};
