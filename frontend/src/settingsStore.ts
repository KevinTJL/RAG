import { ref } from 'vue';
import { api, type SelectedFile, type UserSettings } from './api';

function defaultSettings(): UserSettings {
  return {
    top_k: 4,
    deepseek_thinking_enabled: true,
    deepseek_thinking: {
      'deepseek-v4-flash': true,
      'deepseek-v4-pro': true,
    },
    search_scope: 'all',
    selected_files: [],
    custom_openai: {
      base_url: 'https://api.openai.com/v1',
      model_name: '',
      temperature: null,
      top_p: null,
      max_tokens: null,
      timeout: null,
      enabled_for_chat: false,
      enabled_for_review: false,
      has_api_key: false,
    },
  };
}

const settings = ref<UserSettings>(defaultSettings());
const loading = ref(false);
const saving = ref(false);
const error = ref('');

function normalize(next: Partial<UserSettings> | any): UserSettings {
  const base = defaultSettings();
  const custom = { ...base.custom_openai, ...(next?.custom_openai || {}) };
  const thinking = { ...base.deepseek_thinking, ...(next?.deepseek_thinking || {}) };
  return {
    ...base,
    ...next,
    top_k: Math.max(1, Math.min(8, Number(next?.top_k || base.top_k))),
    selected_files: Array.isArray(next?.selected_files) ? next.selected_files : [],
    deepseek_thinking: thinking,
    custom_openai: custom,
  };
}

async function loadSettings() {
  loading.value = true;
  error.value = '';
  try {
    settings.value = normalize((await api.settings()).settings);
  } catch (e: any) {
    error.value = e?.message || '设置加载失败';
  } finally {
    loading.value = false;
  }
}

async function saveSettings(payload?: any) {
  saving.value = true;
  error.value = '';
  try {
    settings.value = normalize((await api.updateSettings(payload || settings.value)).settings);
  } catch (e: any) {
    error.value = e?.message || '设置保存失败';
    throw e;
  } finally {
    saving.value = false;
  }
}

function selectedFilesForRequest(): SelectedFile[] {
  return settings.value.selected_files || [];
}

function chatQueryOptions() {
  return {
    top_k: settings.value.top_k,
    search_scope: settings.value.search_scope,
    selected_files: selectedFilesForRequest(),
    deepseek_thinking_enabled: settings.value.deepseek_thinking_enabled,
    custom_model_enabled: settings.value.custom_openai.enabled_for_chat,
  };
}

function reviewQueryOptions() {
  return {
    deepseek_thinking_enabled: settings.value.deepseek_thinking_enabled,
    custom_model_enabled: settings.value.custom_openai.enabled_for_review,
  };
}

loadSettings();

export const settingsStore = {
  settings,
  loading,
  saving,
  error,
  loadSettings,
  saveSettings,
  chatQueryOptions,
  reviewQueryOptions,
};
