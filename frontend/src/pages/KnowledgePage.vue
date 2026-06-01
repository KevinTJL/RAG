<template>
  <div class="knowledge-layout">
    <section class="panel file-panel">
      <div class="page-head">
        <div>
          <h1>知识库</h1>
          <p>系统知识库只读；我的知识库支持上传、删除和检索。</p>
          <p class="muted">PDF 文件首次预览需要加载解析资源，较大的文件可能较慢，请耐心等待。</p>
        </div>
        <RouterLink class="button ghost" to="/chat">返回问答</RouterLink>
      </div>

      <label class="upload">
        <input type="file" accept=".txt,.md,.pdf" @change="upload" />
        <span>{{ ingesting ? '正在更新知识库...' : '导入新文档' }}</span>
      </label>

      <div v-if="error" class="error">{{ error }}</div>
      <div class="file-list">
        <h3>系统知识库</h3>
        <button
          v-for="file in systemFiles"
          :key="'system-' + file"
          :class="{ active: selected?.name === file && selected?.scope === 'system' }"
          @click="selected = { name: file, scope: 'system' }"
        >
          <span>{{ file }}</span>
          <small>只读</small>
        </button>
        <div v-if="systemFiles.length === 0" class="empty small">暂无系统知识库文件</div>

        <h3>我的知识库</h3>
        <button
          v-for="file in personalFiles"
          :key="'personal-' + file"
          :class="{ active: selected?.name === file && selected?.scope === 'personal' }"
          @click="selected = { name: file, scope: 'personal' }"
        >
          <span>{{ file }}</span>
          <em @click.stop="remove(file)">删除</em>
        </button>
        <div v-if="personalFiles.length === 0" class="empty small">你还没有上传个人知识库文件</div>
      </div>
    </section>

    <FilePreview :filename="selected?.name || ''" :scope="selected?.scope || 'personal'" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { api } from '../api';
import FilePreview from '../components/FilePreview.vue';

type SelectedFile = { name: string; scope: 'system' | 'personal' };

const systemFiles = ref<string[]>([]);
const personalFiles = ref<string[]>([]);
const selected = ref<SelectedFile | null>(null);
const ingesting = ref(false);
const error = ref('');

async function load() {
  error.value = '';
  try {
    const data = await api.files();
    personalFiles.value = data.personal_files || data.files || [];
    systemFiles.value = data.system_files || [];
  } catch (e: any) {
    personalFiles.value = [];
    systemFiles.value = [];
    error.value = `无法读取知识库文件列表：${e.message}`;
  }
  if (!selected.value && systemFiles.value.length) selected.value = { name: systemFiles.value[0], scope: 'system' };
  if (!selected.value && personalFiles.value.length) selected.value = { name: personalFiles.value[0], scope: 'personal' };
}

async function upload(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (!file) return;
  ingesting.value = true;
  try {
    await api.upload(file);
    await load();
    selected.value = { name: file.name, scope: 'personal' };
  } finally {
    ingesting.value = false;
    (event.target as HTMLInputElement).value = '';
  }
}

async function remove(file: string) {
  if (!confirm(`删除 ${file} 及其关联知识库切片？`)) return;
  await api.deleteFile(file);
  if (selected.value?.name === file && selected.value.scope === 'personal') selected.value = null;
  await load();
}

onMounted(load);
</script>
