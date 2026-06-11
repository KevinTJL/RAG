<template>
  <aside class="profile-panel">
    <div class="profile-card">
      <div class="profile-avatar-slot" aria-hidden="true"></div>
      <section class="profile-content">
        <div class="panel-head">
          <h2>学习画像</h2>
          <button :disabled="loading" @click="$emit('refresh')">{{ loading ? '同步中...' : '刷新' }}</button>
        </div>
        <p v-if="cachedAt" class="cache-note">缓存于 {{ cacheTime }}</p>
        <div v-if="error" class="error small">{{ error }}</div>
        <div v-if="!profile" class="empty">暂无缓存画像</div>
        <template v-else>
          <section class="profile-summary">
            <span>抽象评价</span>
            <p>{{ abstractEvaluation }}</p>
          </section>

          <h3>薄弱概念</h3>
          <div v-if="weakConcepts.length === 0" class="empty small">暂无明显薄弱点</div>
          <button v-for="item in weakConcepts" :key="item.name" class="weak-row" @click="$emit('review', item)">
            <span class="pie" :style="{ background: pie(item.score) }"></span>
            <span>{{ item.name }}</span>
            <b>{{ Math.round(item.score * 100) }}%</b>
            <span class="delete-mini" @click.stop="$emit('delete-tag', { category: 'concept_mastery', value: item.name })">删除</span>
          </button>

          <h3>学习模块</h3>
          <button v-for="item in reviews" :key="item" class="review-link" @click="$emit('review', { name: item, score: 0.4 })">
            <span>{{ item }}</span>
            <span class="delete-mini" @click.stop="$emit('delete-tag', { category: 'recommended_review', value: item })">删除</span>
          </button>

          <h3>薄弱历史</h3>
          <div v-for="item in history" :key="item.concept" class="history-row">
            <span>{{ item.concept }}</span>
            <em>{{ item.status === 'cleared' ? '已熟悉' : '进行中' }}</em>
            <button class="text-delete" @click="$emit('delete-tag', { category: 'weak_history', value: item.concept })">删除</button>
          </div>
        </template>
      </section>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{ profile: any; loading?: boolean; error?: string; cachedAt?: number }>();
defineEmits(['refresh', 'review', 'delete-tag']);

const weakConcepts = computed(() => {
  const mastery = props.profile?.concept_mastery || {};
  return Object.entries(mastery)
    .map(([name, value]: any) => ({ name, score: Number(value.score || 0), status: value.status }))
    .filter((item) => item.score > 0 && item.status !== 'familiar')
    .sort((a, b) => b.score - a.score)
    .slice(0, 8);
});
const reviews = computed(() => (props.profile?.recommended_review || []).slice(0, 6));
const history = computed(() => (props.profile?.weak_history || []).slice(0, 12));
const abstractEvaluation = computed(() => props.profile?.abstract_evaluation || '提问记录还不够多，暂无法形成稳定评价。');
const pie = (score: number) => `conic-gradient(#f59e0b ${Math.round(score * 360)}deg, #e5e7eb 0deg)`;
const cacheTime = computed(() => (props.cachedAt ? new Date(props.cachedAt).toLocaleString() : ''));
</script>
