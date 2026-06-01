<template>
  <div ref="viewerRef" class="pdf-viewer">
    <div class="toolbar">
      <button @click="prev" :disabled="loading || rendering || page <= 1">上一页</button>
      <span>第 {{ page }} / {{ pageCount }} 页</span>
      <form class="page-jump" @submit.prevent="jump">
        <input v-model.number="targetPage" type="number" min="1" :max="pageCount" :disabled="loading || rendering" />
        <button type="submit" :disabled="loading || rendering">跳转</button>
      </form>
      <button @click="next" :disabled="loading || rendering || page >= pageCount">下一页</button>
      <span v-if="loading">加载中...</span>
      <span v-else-if="rendering">渲染中...</span>
    </div>
    <div v-if="errorMessage" class="empty small">{{ errorMessage }}</div>
    <canvas v-show="!errorMessage" ref="canvasRef"></canvas>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import * as pdfjsLib from 'pdfjs-dist';
import workerUrl from 'pdfjs-dist/build/pdf.worker.mjs?url';

const props = defineProps<{ url: string; initialPage?: number }>();
(pdfjsLib as any).GlobalWorkerOptions.workerSrc = workerUrl;

const viewerRef = ref<HTMLDivElement | null>(null);
const canvasRef = ref<HTMLCanvasElement | null>(null);
const page = ref(props.initialPage || 1);
const targetPage = ref(props.initialPage || 1);
const pageCount = ref(1);
const loading = ref(false);
const rendering = ref(false);
const errorMessage = ref('');
let pdfDoc: any = null;
let renderTask: any = null;
let loadTask: any = null;
let renderSerial = 0;
let loadSerial = 0;

function cancelRender() {
  if (!renderTask) return;
  try {
    renderTask.cancel();
  } catch {
    // PDF.js may throw if the task has already settled.
  }
  renderTask = null;
}

function getRenderScale(pdfPage: any) {
  const baseViewport = pdfPage.getViewport({ scale: 1 });
  const availableWidth = Math.max((viewerRef.value?.clientWidth || 0) - 24, 320);
  const fitScale = availableWidth / baseViewport.width;
  return Math.min(Math.max(fitScale, 0.8), 1.2);
}

async function render() {
  if (!pdfDoc || !canvasRef.value) return;
  const serial = ++renderSerial;
  cancelRender();
  rendering.value = true;
  try {
    const pdfPage = await pdfDoc.getPage(page.value);
    if (serial !== renderSerial) return;
    const viewport = pdfPage.getViewport({ scale: getRenderScale(pdfPage) });
    const canvas = canvasRef.value;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    canvas.width = viewport.width;
    canvas.height = viewport.height;
    renderTask = pdfPage.render({ canvasContext: ctx, viewport });
    await renderTask.promise;
  } catch (error: any) {
    if (error?.name !== 'RenderingCancelledException') throw error;
  } finally {
    if (serial === renderSerial) {
      renderTask = null;
      rendering.value = false;
    }
  }
}

async function load() {
  const serial = ++loadSerial;
  cancelRender();
  renderSerial += 1;
  loading.value = true;
  rendering.value = false;
  errorMessage.value = '';
  pdfDoc = null;
  const previousTask = loadTask;
  previousTask?.destroy?.();
  loadTask = (pdfjsLib as any).getDocument({
    url: props.url,
    cMapUrl: '/pdfjs/cmaps/',
    cMapPacked: true,
    standardFontDataUrl: '/pdfjs/standard_fonts/',
    rangeChunkSize: 65536,
  });
  try {
    pdfDoc = await loadTask.promise;
    if (serial !== loadSerial) return;
    pageCount.value = pdfDoc.numPages;
    page.value = Math.min(Math.max(props.initialPage || 1, 1), pageCount.value);
    targetPage.value = page.value;
    await nextTick();
    await render();
  } catch (error: any) {
    if (serial === loadSerial && error?.name !== 'RenderingCancelledException') {
      errorMessage.value = 'PDF 加载失败，请刷新页面或重新选择文件。';
    }
  } finally {
    if (serial === loadSerial) {
      loading.value = false;
    }
  }
}

function prev() {
  if (page.value > 1) page.value -= 1;
}

function next() {
  if (page.value < pageCount.value) page.value += 1;
}

function jump() {
  const nextPage = Number(targetPage.value);
  if (!Number.isFinite(nextPage)) return;
  page.value = Math.min(Math.max(Math.trunc(nextPage), 1), pageCount.value);
}

watch(page, async () => {
  targetPage.value = page.value;
  await render();
});
watch(() => props.url, load);
watch(() => props.initialPage, async () => {
  if (!pdfDoc) return;
  page.value = Math.min(Math.max(props.initialPage || 1, 1), pageCount.value);
  targetPage.value = page.value;
  await render();
});
onMounted(load);
onBeforeUnmount(() => {
  cancelRender();
  renderSerial += 1;
  loadSerial += 1;
  if (loadTask?.destroy) {
    loadTask.destroy();
  }
});
</script>
