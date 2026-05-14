<template>
  <section class="panel preview">
    <div class="panel-head">
      <h2>{{ filename || '文件预览' }}</h2>
      <span v-if="preview?.type">{{ preview.type }}</span>
    </div>
    <div v-if="!filename" class="empty">选择一个知识库文件进行在线查阅。</div>
    <div v-else-if="loading" class="empty">加载中...</div>
    <PdfViewer v-else-if="preview?.type === 'pdf'" :url="rawUrl" :initial-page="page || 1" />
    <MarkdownView v-else-if="preview?.type === 'md'" :text="preview.content || ''" />
    <pre v-else class="text-preview">{{ preview?.content }}</pre>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { api } from '../api';
import PdfViewer from './PdfViewer.vue';
import MarkdownView from './MarkdownView.vue';

const props = defineProps<{ filename: string; scope?: 'system' | 'personal'; page?: number }>();
const preview = ref<any>(null);
const loading = ref(false);
const rawUrl = computed(() => (props.filename ? api.rawFileUrl(props.filename, props.scope || 'personal') : ''));

async function load() {
  preview.value = null;
  if (!props.filename) return;
  loading.value = true;
  try {
    preview.value = await api.previewFile(props.filename, props.scope || 'personal');
  } finally {
    loading.value = false;
  }
}

watch(() => [props.filename, props.scope], load, { immediate: true });
</script>
