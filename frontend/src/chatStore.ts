import { reactive, ref } from 'vue';
import { api, getUserId } from './api';

const userId = getUserId();
const messagesKey = `local_rag_messages_${userId}`;
const profileCacheKey = `local_rag_profile_${userId}`;
const selectedChatModelKey = 'local_rag_selected_chat_model';

const messages = ref<any[]>(JSON.parse(localStorage.getItem(messagesKey) || '[]'));
const answering = ref(false);
const profile = ref<any>(null);
const profileLoading = ref(false);
const profileError = ref('');
const profileCachedAt = ref(0);
const builtInChatModels = ['qwen2.5:3b', 'deepseek-v4-pro', 'deepseek-v4-flash'];
const chatModels = ref<string[]>([...builtInChatModels]);
const selectedChatModel = ref(localStorage.getItem(selectedChatModelKey) || 'qwen2.5:3b');
const pendingQuestions = reactive<Set<string>>(new Set());

function apiRole(role: string) {
  return role === 'bot' ? 'assistant' : role;
}

function saveMessages() {
  localStorage.setItem(messagesKey, JSON.stringify(messages.value));
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
      localStorage.setItem(selectedChatModelKey, selectedChatModel.value);
    }
  } catch {
    // Keep the built-in model list when the backend is temporarily unavailable.
  }
}

function setSelectedChatModel(model: string) {
  selectedChatModel.value = model;
  localStorage.setItem(selectedChatModelKey, model);
}

async function sendQuestion(question: string) {
  const trimmed = question.trim();
  if (!trimmed || answering.value) return;

  const requestId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  messages.value.push({ role: 'user', content: trimmed, requestId });
  answering.value = true;
  pendingQuestions.add(requestId);
  saveMessages();

  const history = messages.value.slice(-5, -1).map(({ role, content }) => ({ role: apiRole(role), content }));
  try {
    const data = await api.query({ question: trimmed, user_id: userId, history, chat_model: selectedChatModel.value });
    messages.value.push({
      role: 'bot',
      content: data.answer,
      chunks: data.chunks || [],
      followups: data.followups || [],
      learningInsight: data.learning_insight,
      requestId,
    });
    saveProfileCache(data.profile || profile.value);
  } catch (error: any) {
    messages.value.push({
      role: 'bot',
      content: `回答生成失败：${error?.message || '请求失败'}`,
      requestId,
    });
  } finally {
    pendingQuestions.delete(requestId);
    answering.value = pendingQuestions.size > 0;
    saveMessages();
  }
}

async function clearChatHistory() {
  messages.value = [];
  localStorage.removeItem(messagesKey);
  await loadProfile();
}

async function clearAllHistory() {
  const data = await api.clearAllHistory(userId);
  messages.value = [];
  localStorage.removeItem(messagesKey);
  localStorage.removeItem(profileCacheKey);
  profile.value = data.profile || null;
  profileCachedAt.value = 0;
  profileError.value = '';
}

async function deleteMessageGroup(index: number) {
  const current = messages.value[index];
  if (!current) return;

  if (current.requestId) {
    messages.value = messages.value.filter((message) => message.requestId !== current.requestId);
  } else {
    const start = current.role === 'bot' && messages.value[index - 1]?.role === 'user' ? index - 1 : index;
    const count = messages.value[start]?.role === 'user' && messages.value[start + 1]?.role === 'bot' ? 2 : 1;
    messages.value.splice(start, count);
  }

  saveMessages();
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
  messages,
  answering,
  profile,
  profileLoading,
  profileError,
  profileCachedAt,
  chatModels,
  selectedChatModel,
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
