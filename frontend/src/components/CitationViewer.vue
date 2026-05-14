<template>
  <div v-if="chunk" class="drawer">
    <div class="drawer-head">
      <div>
        <h2>{{ chunk.source }}</h2>
        <p>引用分块，距离 {{ chunk.distance }}</p>
      </div>
      <button @click="$emit('close')">关闭</button>
    </div>
    <FilePreview
      :filename="chunk.source"
      :scope="chunk.scope || 'system'"
      :page="chunk.page > 0 ? chunk.page : 1"
    />
    <details open class="source-chunk">
      <summary>检索命中的文本分块</summary>
      <p>{{ chunk.text }}</p>
    </details>
  </div>
</template>

<script setup lang="ts">
import FilePreview from './FilePreview.vue';
defineProps<{ chunk: any | null }>();
defineEmits(['close']);
</script>
