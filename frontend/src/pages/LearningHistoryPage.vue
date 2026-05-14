<template>
  <div class="history-page">
    <section class="panel history-list-pane">
      <div class="page-head">
        <div>
          <h1>学习历史</h1>
          <p>查看已经完成的学习试卷、作答记录和判题反馈。</p>
        </div>
        <RouterLink class="button ghost" to="/review">返回学习</RouterLink>
      </div>

      <div v-if="completedSessions.length === 0" class="empty">暂无已完成的学习记录</div>
      <button
        v-for="item in completedSessions"
        :key="item.id"
        class="history-item"
        :class="{ active: selected?.id === item.id }"
        @click="selected = item"
      >
        <span>
          <b>{{ item.topic }}</b>
          <em>难度 {{ item.difficulty || item.plan?.difficulty || 1 }} · 得分 {{ Math.round((item.score || 0) * 100) }}%</em>
        </span>
        <span class="delete-mini" @click.stop="deleteHistory(item.id)">删除</span>
      </button>
    </section>

    <section class="panel history-detail-pane">
      <div v-if="!selected" class="empty">选择一条学习记录查看详情</div>
      <template v-else>
        <h2>{{ selected.plan?.topic || selected.topic }}</h2>
        <p class="cache-note">
          {{ selected.completed_at || selected.updated_at || selected.created_at }}
        </p>
        <article v-for="step in selected.plan?.steps || []" :key="step.id" class="step">
          <h3>{{ step.title }}</h3>
          <MarkdownView v-if="step.type === 'explain'" :text="step.content || ''" />
          <template v-else>
            <MarkdownView :text="step.question || ''" />
            <div class="history-answer">
              <b>你的答案</b>
              <MarkdownView :text="answerOf(step.id).answer || '未作答'" />
            </div>
            <div class="history-answer" :class="answerOf(step.id).is_correct ? 'ok' : 'bad'">
              <b>{{ answerOf(step.id).is_correct ? '正确' : '需要复习' }}</b>
              <MarkdownView :text="answerOf(step.id).feedback || step.explanation || ''" />
            </div>
          </template>
        </article>
      </template>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { api, getUserId } from '../api';
import MarkdownView from '../components/MarkdownView.vue';

const userId = getUserId();
const sessions = ref<any[]>([]);
const selected = ref<any>(null);
const completedSessions = computed(() => sessions.value.filter((item) => item.status === 'completed'));

function answerOf(stepId: string) {
  return selected.value?.answers?.[stepId] || {};
}

async function loadHistory() {
  sessions.value = (await api.reviewHistory(userId)).sessions;
  if (!selected.value || !completedSessions.value.some((item) => item.id === selected.value.id)) {
    selected.value = completedSessions.value[0] || null;
  }
}

async function deleteHistory(sessionId: string) {
  if (!confirm('确定要删除这张已完成的学习试卷吗？')) return;
  const data = await api.deleteReviewSession(userId, sessionId);
  sessions.value = data.sessions;
  if (selected.value?.id === sessionId) {
    selected.value = completedSessions.value[0] || null;
  }
}

onMounted(async () => {
  await loadHistory();
});
</script>
