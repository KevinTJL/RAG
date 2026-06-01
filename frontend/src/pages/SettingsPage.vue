<template>
  <div class="settings-page">
    <section class="panel settings-main">
      <div class="page-head">
        <div>
          <h1>用户设置</h1>
          <p>调整问答检索、DeepSeek thinking 和私人 OpenAI API 格式模型。</p>
        </div>
        <div class="head-actions">
          <button class="button ghost" type="button" :disabled="loading" @click="refresh">刷新</button>
          <button type="button" :disabled="saving" @click="save">{{ saving ? '保存中...' : '保存设置' }}</button>
        </div>
      </div>

      <div v-if="error" class="error">{{ error }}</div>
      <div v-if="savedMessage" class="success-note">{{ savedMessage }}</div>

      <div class="settings-grid">
        <section class="settings-section">
          <h2>检索设置</h2>
          <label class="field-row">
            <span>文本块召回数量</span>
            <input v-model.number="draft.top_k" type="number" min="1" max="8" />
          </label>
          <div class="settings-subsection">
            <h3>DeepSeek Thinking 模式</h3>
            <p class="hint">按模型单独控制是否启用深度思考。开启后模型会先推理再作答，质量更高但耗时更长。</p>
            <label class="check-row" v-for="model in deepseekModels" :key="model">
              <input
                type="checkbox"
                :checked="draft.deepseek_thinking?.[model] ?? true"
                @change="setDeepseekThinking(model, ($event.target as HTMLInputElement).checked)"
              />
              <span>{{ model }} 开启 thinking</span>
            </label>
          </div>
          <label class="field-row">
            <span>检索范围</span>
            <select v-model="draft.search_scope">
              <option value="all">全部知识库</option>
              <option value="personal">仅个人 RAG 库</option>
              <option value="system">仅系统知识库</option>
            </select>
          </label>
          <p class="hint">不勾选具体文件时，会在当前检索范围内搜索全部文件。</p>
        </section>

        <section class="settings-section">
          <h2>私人 OpenAI API 格式模型</h2>
          <p class="hint">需要兼容 OpenAI Chat Completions API。API key 会加密保存在后端，页面不会回显明文。</p>
          <label class="field-row">
            <span>API Key</span>
            <input v-model="draft.custom_openai.api_key" type="password" :placeholder="draft.custom_openai.has_api_key ? '已保存，留空表示不修改' : '必填'" />
          </label>
          <label class="check-row">
            <input v-model="draft.custom_openai.clear_api_key" type="checkbox" />
            <span>清除已保存 API key</span>
          </label>
          <label class="field-row">
            <span>Base URL</span>
            <input v-model="draft.custom_openai.base_url" placeholder="https://api.openai.com/v1" />
          </label>
          <label class="field-row">
            <span>模型名称</span>
            <input v-model="draft.custom_openai.model_name" placeholder="gpt-4.1-mini" />
          </label>
          <div class="settings-columns">
            <label class="field-row">
              <span>temperature</span>
              <input v-model="draft.custom_openai.temperature" type="number" step="0.1" placeholder="默认" />
            </label>
            <label class="field-row">
              <span>top_p</span>
              <input v-model="draft.custom_openai.top_p" type="number" step="0.1" placeholder="默认" />
            </label>
            <label class="field-row">
              <span>max_tokens</span>
              <input v-model="draft.custom_openai.max_tokens" type="number" placeholder="默认" />
            </label>
            <label class="field-row">
              <span>timeout 秒</span>
              <input v-model="draft.custom_openai.timeout" type="number" placeholder="默认" />
            </label>
          </div>
          <label class="check-row">
            <input v-model="draft.custom_openai.enabled_for_chat" type="checkbox" />
            <span>问答模块使用私人模型</span>
          </label>
          <label class="check-row">
            <input v-model="draft.custom_openai.enabled_for_review" type="checkbox" />
            <span>学习计划模块使用私人模型</span>
          </label>
          <button class="button ghost" type="button" :disabled="testingOpenAI || saving || !draft.custom_openai.model_name" @click="testOpenAI">
            {{ testingOpenAI ? '测试中...' : '测试 OpenAI 连接' }}
          </button>
        </section>
      </div>
    </section>

    <section class="panel settings-files">
      <div class="panel-head">
        <h2>搜索文件</h2>
        <div class="head-actions">
          <button class="button ghost" type="button" @click="selectVisibleFiles">全部勾选</button>
          <button class="button ghost" type="button" @click="loadFiles">刷新文件</button>
        </div>
      </div>
      <div class="file-choice-grid">
        <div>
          <h3>系统知识库</h3>
          <label v-for="file in visibleSystemFiles" :key="`system-${file}`" class="check-row">
            <input type="checkbox" :checked="isSelected('system', file)" @change="toggleFile('system', file)" />
            <span>{{ file }}</span>
          </label>
          <div v-if="!visibleSystemFiles.length" class="empty small">暂无系统文件</div>
        </div>
        <div>
          <h3>个人 RAG 库</h3>
          <label v-for="file in visiblePersonalFiles" :key="`personal-${file}`" class="check-row">
            <input type="checkbox" :checked="isSelected('personal', file)" @change="toggleFile('personal', file)" />
            <span>{{ file }}</span>
          </label>
          <div v-if="!visiblePersonalFiles.length" class="empty small">暂无个人文件</div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';
import { api, type KnowledgeScope, type UserSettings } from '../api';
import { chatStore } from '../chatStore';
import { settingsStore } from '../settingsStore';

const loading = settingsStore.loading;
const saving = settingsStore.saving;
const error = settingsStore.error;
const savedMessage = ref('');
const testingOpenAI = ref(false);
const systemFiles = ref<string[]>([]);
const personalFiles = ref<string[]>([]);
const draft = reactive<any>(cloneSettings(settingsStore.settings.value));

const visibleSystemFiles = computed(() => (draft.search_scope === 'personal' ? [] : systemFiles.value));
const visiblePersonalFiles = computed(() => (draft.search_scope === 'system' ? [] : personalFiles.value));

const deepseekModels = computed(() =>
  (chatStore.chatModels.value || []).filter((m: string) => m.startsWith('deepseek-'))
);

function setDeepseekThinking(model: string, enabled: boolean) {
  if (!draft.deepseek_thinking) draft.deepseek_thinking = {};
  draft.deepseek_thinking[model] = enabled;
}

function cloneSettings(settings: UserSettings) {
  return JSON.parse(JSON.stringify({
    ...settings,
    custom_openai: {
      ...settings.custom_openai,
      api_key: '',
      clear_api_key: false,
    },
  }));
}

function syncDraft() {
  Object.assign(draft, cloneSettings(settingsStore.settings.value));
  ensureDefaultFileSelection();
}

async function refresh() {
  await settingsStore.loadSettings();
  syncDraft();
  await loadFiles();
}

function selectedKey(scope: KnowledgeScope, source: string) {
  return `${scope}:${source}`;
}

function isSelected(scope: KnowledgeScope, source: string) {
  return (draft.selected_files || []).some((item: any) => item.scope === scope && item.source === source);
}

function allVisibleFileChoices() {
  return [
    ...visibleSystemFiles.value.map((source) => ({ scope: 'system' as KnowledgeScope, source })),
    ...visiblePersonalFiles.value.map((source) => ({ scope: 'personal' as KnowledgeScope, source })),
  ];
}

function ensureDefaultFileSelection() {
  const choices = allVisibleFileChoices();
  if (choices.length && (!Array.isArray(draft.selected_files) || draft.selected_files.length === 0)) {
    draft.selected_files = choices;
  }
}

function selectVisibleFiles() {
  draft.selected_files = allVisibleFileChoices();
}

function toggleFile(scope: KnowledgeScope, source: string) {
  const key = selectedKey(scope, source);
  const selected = new Set((draft.selected_files || []).map((item: any) => selectedKey(item.scope, item.source)));
  if (selected.has(key)) {
    if (selected.size <= 1) {
      savedMessage.value = '至少保留一个搜索文件。';
      return;
    }
    draft.selected_files = draft.selected_files.filter((item: any) => selectedKey(item.scope, item.source) !== key);
  } else {
    draft.selected_files = [...(draft.selected_files || []), { scope, source }];
  }
}

function normalizedPayload() {
  const custom = { ...draft.custom_openai };
  for (const key of ['temperature', 'top_p', 'max_tokens', 'timeout']) {
    if (custom[key] === '') custom[key] = null;
  }
  return {
    top_k: Math.max(1, Math.min(8, Number(draft.top_k || 4))),
    deepseek_thinking_enabled: Boolean(draft.deepseek_thinking_enabled),
    deepseek_thinking: draft.deepseek_thinking || {},
    search_scope: draft.search_scope,
    selected_files: (draft.selected_files && draft.selected_files.length ? draft.selected_files : allVisibleFileChoices()),
    custom_openai: custom,
  };
}

async function save() {
  savedMessage.value = '';
  await settingsStore.saveSettings(normalizedPayload());
  syncDraft();
  await chatStore.loadModels();
  savedMessage.value = '设置已保存。';
}

async function testOpenAI() {
  testingOpenAI.value = true;
  savedMessage.value = '';
  try {
    await save();
    const result = await api.testOpenAISettings();
    savedMessage.value = `${result.message}${result.preview ? `：${result.preview}` : ''}`;
  } catch (e: any) {
    error.value = e?.message || 'OpenAI 连接测试失败';
  } finally {
    testingOpenAI.value = false;
  }
}

async function loadFiles() {
  const data = await api.files();
  systemFiles.value = data.system_files || [];
  personalFiles.value = data.personal_files || data.files || [];
  ensureDefaultFileSelection();
}

watch(settingsStore.settings, syncDraft);
refresh();
</script>
