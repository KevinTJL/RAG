<template>
  <div class="pdf-viewer">
    <div class="toolbar">
      <button @click="prev" :disabled="page <= 1">上一页</button>
      <span>第 {{ page }} / {{ pageCount }} 页</span>
      <form class="page-jump" @submit.prevent="jump">
        <input v-model.number="targetPage" type="number" min="1" :max="pageCount" />
        <button type="submit">跳转</button>
      </form>
      <button @click="next" :disabled="page >= pageCount">下一页</button>
    </div>
    <canvas ref="canvasRef"></canvas>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue';
import * as pdfjsLib from 'pdfjs-dist';
import workerUrl from 'pdfjs-dist/build/pdf.worker.mjs?url';

const props = defineProps<{ url: string; initialPage?: number }>();
(pdfjsLib as any).GlobalWorkerOptions.workerSrc = workerUrl;

const canvasRef = ref<HTMLCanvasElement | null>(null);
const page = ref(props.initialPage || 1);
const targetPage = ref(props.initialPage || 1);
const pageCount = ref(1);
let pdfDoc: any = null;

async function render() {
  if (!pdfDoc || !canvasRef.value) return;
  const pdfPage = await pdfDoc.getPage(page.value);
  const viewport = pdfPage.getViewport({ scale: 1.35 });
  const canvas = canvasRef.value;
  const ctx = canvas.getContext('2d');
  canvas.width = viewport.width;
  canvas.height = viewport.height;
  await pdfPage.render({ canvasContext: ctx, viewport }).promise;
}

async function load() {
  pdfDoc = await (pdfjsLib as any).getDocument({
    url: props.url,
    cMapUrl: '/pdfjs/cmaps/',
    cMapPacked: true,
    standardFontDataUrl: '/pdfjs/standard_fonts/',
  }).promise;
  pageCount.value = pdfDoc.numPages;
  page.value = Math.min(Math.max(props.initialPage || 1, 1), pageCount.value);
  targetPage.value = page.value;
  await render();
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
</script>
