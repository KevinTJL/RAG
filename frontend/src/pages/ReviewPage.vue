<template>
  <div class="review-layout">
    <section class="panel review-main">
      <div class="page-head">
        <div>
          <h1>学习计划</h1>
          <p>生成讲解、问答和做题任务，完成后自动调整薄弱度。</p>
        </div>
        <div class="head-actions">
          <label class="model-picker">
            <span>出题模型</span>
            <select v-model="selectedChatModel" :disabled="loading" @change="setSelectedChatModel(selectedChatModel)">
              <option v-for="model in chatModels" :key="model" :value="model">{{ model }}</option>
            </select>
          </label>
          <RouterLink class="button ghost" to="/chat">返回问答</RouterLink>
        </div>
      </div>

      <form class="review-form" @submit.prevent="createPlan">
        <input v-model="topic" placeholder="输入要学习的概念" />
        <select v-model.number="selectedDifficulty" :disabled="loading">
          <option v-for="level in difficultyOptions" :key="level.value" :value="level.value">{{ level.label }}</option>
        </select>
        <button :disabled="loading || !topic.trim()">{{ loading ? '生成中...' : '生成学习计划' }}</button>
      </form>

      <div v-if="session" class="plan">
        <div class="plan-meta">
          <span>{{ session.status === 'completed' ? '已完成' : '进行中' }}</span>
          <span>得分 {{ Math.round((session.score || 0) * 100) }}%</span>
          <span>难度 {{ session.difficulty || session.plan.difficulty || 1 }}</span>
        </div>
        <h2>{{ session.plan.topic }}</h2>
        <p>{{ session.plan.overview }}</p>
        <article
          v-for="(step, index) in session.plan.steps"
          :key="step.id || index"
          :ref="(el) => setStepEl(el, index)"
          class="step"
          :class="{ active: activeStepIndex === index }"
          @click="activeStepIndex = index"
        >
          <div class="step-head">
            <h3>{{ step.title }}</h3>
            <button class="text-delete" type="button" @click="deleteStep(step, index)">删除模块</button>
          </div>
          <MarkdownView v-if="step.type === 'explain'" :text="step.content" />

          <div v-else-if="step.type === 'question'">
            <MarkdownView :text="step.question" />
            <textarea v-model="answers[step.id]" placeholder="写下你的回答"></textarea>
            <button type="button" @click="submitAnswer(step)">提交回答</button>
            <MarkdownView
              v-if="feedback[step.id]"
              class="review-feedback"
              :class="feedback[step.id].is_correct ? 'ok' : 'bad'"
              :text="feedback[step.id].feedback"
            />
          </div>

          <div v-else-if="step.type === 'blank'">
            <MarkdownView :text="step.question" />
            <input v-model="answers[step.id]" class="blank-input" placeholder="填写答案" />
            <MarkdownView
              v-if="feedback[step.id]"
              class="review-feedback"
              :class="feedback[step.id].is_correct ? 'ok' : 'bad'"
              :text="feedback[step.id].feedback"
            />
          </div>

          <div v-else-if="step.type === 'quiz'">
            <MarkdownView :text="normalizedQuiz(step).question" />
            <button
              v-for="option in normalizedQuiz(step).options"
              :key="option"
              class="option"
              :class="{ selected: isSelectedOption(step, option) }"
              type="button"
              @click="choose(step, option)"
            >
              <MarkdownView :text="option" />
            </button>
            <MarkdownView
              v-if="feedback[step.id]"
              class="review-feedback"
              :class="feedback[step.id].is_correct ? 'ok' : 'bad'"
              :text="feedback[step.id].feedback"
            />
          </div>
        </article>
        <button class="complete" type="button" :disabled="submittingPaper" @click="submitPaper">
          {{ submittingPaper ? '提交中...' : '提交当前答卷' }}
        </button>
      </div>
    </section>

    <section class="review-side">
      <div class="review-side-pane">
        <button class="complete comprehensive-button" type="button" :disabled="loading" @click="createComprehensivePlan">
          综合试卷
        </button>
        <ProfilePanel
          :profile="profile"
          :loading="profileLoading"
          :error="profileError"
          :cached-at="profileCachedAt"
          @refresh="loadProfile"
          @review="goReview"
          @delete-tag="deleteProfileTag"
        />
      </div>

      <div class="panel review-side-pane review-history-pane">
        <h2>正在学习</h2>
        <button
          v-for="item in activeHistory"
          :key="item.id"
          class="history-item"
          :class="{ active: activeHistoryId === item.id }"
          @click="restoreSession(item)"
        >
          <span>
            <b>{{ item.topic }}</b>
            <em>{{ item.status }} · 得分 {{ Math.round((item.score || 0) * 100) }}%</em>
          </span>
          <span class="delete-mini" @click.stop="deleteSession(item.id)">删除</span>
        </button>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';
import { api, getUserId } from '../api';
import { chatStore } from '../chatStore';
import MarkdownView from '../components/MarkdownView.vue';
import ProfilePanel from '../components/ProfilePanel.vue';

const route = useRoute();
const userId = getUserId();
const topic = ref(String(route.query.topic || ''));
const weakScore = Number(route.query.score || 0);
const difficultyOptions = [
  { value: 1, label: '1级 简单' },
  { value: 2, label: '2级 基础' },
  { value: 3, label: '3级 标准' },
  { value: 4, label: '4级 提高' },
  { value: 5, label: '5级 困难' },
];
const selectedDifficulty = ref(weakScore > 0 ? difficultyFromWeakness(weakScore) : 3);
const loading = ref(false);
const submittingPaper = ref(false);
const session = ref<any>(null);
const history = ref<any[]>([]);
const answers = ref<Record<string, string>>({});
const feedback = ref<Record<string, any>>({});
const activeHistoryId = ref('');
const activeStepIndex = ref(0);
const stepEls = ref<HTMLElement[]>([]);
const profile = chatStore.profile;
const profileLoading = chatStore.profileLoading;
const profileError = chatStore.profileError;
const profileCachedAt = chatStore.profileCachedAt;
const chatModels = chatStore.chatModels;
const selectedChatModel = chatStore.selectedChatModel;
const setSelectedChatModel = chatStore.setSelectedChatModel;
const activeHistory = computed(() => history.value.filter((item) => item.status !== 'completed'));

async function loadHistory() {
  history.value = (await api.reviewHistory(userId)).sessions;
}

function restoreSession(item: any) {
  session.value = item;
  activeHistoryId.value = item.id || '';
  activeStepIndex.value = 0;
  stepEls.value = [];
  topic.value = item.topic || '';
  answers.value = Object.fromEntries(
    Object.entries(item.answers || {}).map(([stepId, answer]: [string, any]) => [stepId, answer.answer || '']),
  );
  feedback.value = Object.fromEntries(
    Object.entries(item.answers || {}).map(([stepId, answer]: [string, any]) => [
      stepId,
      { is_correct: Boolean(answer.is_correct), feedback: answer.feedback || '' },
    ]),
  );
}

function setStepEl(el: Element | null, index: number) {
  if (el instanceof HTMLElement) {
    stepEls.value[index] = el;
  }
}

async function scrollToStep(index: number) {
  activeStepIndex.value = index;
  await nextTick();
  stepEls.value[index]?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function splitOptionText(text: string) {
  const normalized = String(text || '').replace(/\s+/g, ' ').trim();
  if (!normalized) return [];
  const parts = normalized.split(/\s*(?=[A-H][.、．]\s*)/).map((item) => item.trim()).filter(Boolean);
  return parts.length > 1 ? parts : [normalized];
}

function extractLabeledOptions(text: string) {
  const normalized = String(text || '').replace(/\s+/g, ' ').trim();
  const matches = [...normalized.matchAll(/(?:^|\s)([A-H])[\.\、．]\s*([\s\S]*?)(?=\s+[A-H][\.\、．]\s*|$)/g)];
  return matches
    .map((match) => `${match[1]}. ${match[2].trim()}`)
    .filter((item) => item.length > 3);
}

function optionLabel(option: string) {
  return String(option || '').trim().match(/^([A-H])(?:[\.\、．]|\s*$)/)?.[1] || '';
}

function optionText(option: string) {
  return String(option || '').trim().replace(/^[A-H][\.\、．]\s*/, '').trim();
}

function normalizeOption(option: string) {
  const label = optionLabel(option);
  const text = optionText(option);
  return label && text ? `${label}. ${text}` : String(option || '').trim();
}

function normalizedQuiz(step: any) {
  const question = String(step.question || '');
  const rawOptions = Array.isArray(step.options) ? step.options : [step.options].filter(Boolean);
  const fromOptions = rawOptions.flatMap((option: any) => splitOptionText(String(option)));
  const fromQuestion = extractLabeledOptions(step.question || '');
  const merged = [...fromQuestion, ...fromOptions].map(normalizeOption).filter(Boolean);
  const byLabel = new Map<string, string>();
  const unlabeled: string[] = [];

  for (const option of merged) {
    const label = optionLabel(option);
    if (!label) {
      unlabeled.push(option);
      continue;
    }

    const current = byLabel.get(label);
    if (!current || option.length > current.length) {
      byLabel.set(label, option);
    }
  }

  const labeled = [...byLabel.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([, option]) => option);
  const questionStart = question.search(/(?:^|\s)[A-H][\.\、．]\s*/);
  const cleanQuestion = questionStart > 0 ? question.slice(0, questionStart).trim() : question;

  return {
    question: cleanQuestion,
    options: labeled.length ? labeled : unlabeled,
  };
}

function isSelectedOption(step: any, option: string) {
  const selected = answers.value[step.id] || '';
  return selected === option || Boolean(optionLabel(selected) && optionLabel(selected) === optionLabel(option));
}

function clampDifficulty(value: any) {
  const level = Number(value || 3);
  return Math.max(1, Math.min(5, Number.isFinite(level) ? Math.round(level) : 3));
}

function difficultyFromWeakness(score: any) {
  const weakness = Math.max(0, Math.min(1, Number(score || 0)));
  if (weakness >= 0.99) return 1;
  if (weakness >= 0.8) return 2;
  if (weakness >= 0.6) return 3;
  if (weakness >= 0.4) return 4;
  return 5;
}

async function createPlan() {
  loading.value = true;
  try {
    const created = (await api.createReviewPlan({
      user_id: userId,
      topic: topic.value,
      weak_score: weakScore,
      difficulty: clampDifficulty(selectedDifficulty.value),
      mode: 'topic',
      chat_model: selectedChatModel.value,
    })).session;
    restoreSession(created);
    await loadHistory();
  } finally {
    loading.value = false;
  }
}

async function createPlanFor(item: any) {
  const nextTopic = String(item?.name || item || '').trim();
  if (!nextTopic) return;
  topic.value = nextTopic;
  const score = Number(item?.score || 0);
  if (score > 0) {
    selectedDifficulty.value = difficultyFromWeakness(score);
  }
  session.value = null;
  answers.value = {};
  feedback.value = {};
  activeHistoryId.value = '';
  activeStepIndex.value = 0;
  loading.value = true;
  try {
    const created = (await api.createReviewPlan({
      user_id: userId,
      topic: nextTopic,
      weak_score: score,
      difficulty: clampDifficulty(selectedDifficulty.value),
      mode: 'topic',
      chat_model: selectedChatModel.value,
    })).session;
    restoreSession(created);
    await loadHistory();
  } finally {
    loading.value = false;
  }
}

async function submitAnswer(step: any) {
  const data = await api.answerReview({ user_id: userId, session_id: session.value.id, step_id: step.id, answer: answers.value[step.id] || '' });
  feedback.value[step.id] = data;
  session.value = data.session;
  await loadHistory();
}

async function choose(step: any, option: string) {
  answers.value[step.id] = option;
}

function quizSteps() {
  return (session.value?.plan?.steps || []).filter((step: any) => ['quiz', 'blank'].includes(step.type));
}

function isCurrentPaper(sessionItem: any) {
  const steps = sessionItem?.plan?.steps || [];
  return steps.filter((step: any) => ['quiz', 'blank'].includes(step.type)).length >= 5;
}

function nextDifficulty() {
  return session.value ? clampDifficulty(Number(session.value.difficulty || session.value.plan?.difficulty || selectedDifficulty.value)) : clampDifficulty(selectedDifficulty.value);
}

function currentWeakScore(profileData: any, concept: string) {
  const mastery = profileData?.concept_mastery || {};
  const item = mastery[concept];
  return Number(item?.score || 0);
}

async function submitPaper() {
  if (!session.value || submittingPaper.value) return;
  const unanswered = quizSteps().filter((step: any) => !answers.value[step.id]);
  if (unanswered.length > 0 && !confirm(`还有 ${unanswered.length} 道题未作答，确定提交吗？`)) return;

  submittingPaper.value = true;
  try {
    for (const step of quizSteps()) {
      if (!answers.value[step.id]) continue;
      const data = await api.answerReview({
        user_id: userId,
        session_id: session.value.id,
        step_id: step.id,
        answer: answers.value[step.id],
      });
      feedback.value[step.id] = data;
      session.value = data.session;
    }

    const data = await api.completeReview({ user_id: userId, session_id: session.value.id, completed: true });
    const completedTopic = session.value.topic;
    const nextLevel = clampDifficulty(data.next_difficulty || nextDifficulty());
    session.value = data.session;
    chatStore.saveProfileCache(data.profile);
    await loadHistory();

    const weakScore = currentWeakScore(data.profile, completedTopic);
    const resultText = data.result === 'excellent' ? '优秀' : data.result === 'passed' ? '及格' : '不及格';
    alert(`本套答对 ${data.correct_count || 0}/${data.total_count || 5} 题，结果：${resultText}。系统将生成下一张 ${nextLevel} 级试卷。`);
    selectedDifficulty.value = nextLevel;
    const created = (await api.createReviewPlan({
      user_id: userId,
      topic: completedTopic,
      weak_score: weakScore,
      difficulty: nextLevel,
      mode: 'topic',
      chat_model: selectedChatModel.value,
    })).session;
    restoreSession(created);
    await loadHistory();
  } finally {
    submittingPaper.value = false;
  }
}

async function complete(done: boolean) {
  const data = await api.completeReview({ user_id: userId, session_id: session.value.id, completed: done });
  session.value = data.session;
  chatStore.saveProfileCache(data.profile);
  await loadHistory();
  alert(data.weakness_delta < 0 ? '学习完成，薄弱度已降低。' : '学习效果不足，薄弱度已提高。');
}

async function loadProfile() {
  await chatStore.loadProfile();
}

async function createComprehensivePlan() {
  loading.value = true;
  try {
    const created = (await api.createReviewPlan({
      user_id: userId,
      topic: '综合学习画像试卷',
      weak_score: 0,
      difficulty: clampDifficulty(selectedDifficulty.value),
      mode: 'comprehensive',
      chat_model: selectedChatModel.value,
    })).session;
    restoreSession(created);
    await loadHistory();
  } finally {
    loading.value = false;
  }
}

async function goReview(item: any) {
  await createPlanFor(item);
}

async function deleteProfileTag(item: { category: string; value: string }) {
  await chatStore.deleteProfileTag(item);
}

async function deleteSession(sessionId: string) {
  if (!confirm('确定要删除这个学习计划吗？')) return;
  const data = await api.deleteReviewSession(userId, sessionId);
  history.value = data.sessions;
  if (session.value?.id === sessionId) {
    session.value = null;
    answers.value = {};
    feedback.value = {};
  }
}

async function deleteStep(step: any, index: number) {
  if (!session.value || !confirm('确定要删除这个学习模块吗？')) return;
  const stepKey = String(step?.id || index);
  try {
    const data = await api.deleteReviewStep(userId, session.value.id, stepKey);
    restoreSession(data.session);
    await loadHistory();
  } catch (error: any) {
    alert(error?.message || '删除学习模块失败');
  }
}

onMounted(async () => {
  chatStore.loadProfileCache();
  await loadHistory();
  const sameTopicSession = history.value.find(
    (item) => item.topic === topic.value && item.status !== 'completed' && isCurrentPaper(item),
  );
  const activeSession = history.value.find((item) => item.status !== 'completed' && isCurrentPaper(item));
  if (sameTopicSession) {
    restoreSession(sameTopicSession);
  } else if (topic.value) {
    await createPlan();
  } else if (activeSession) {
    restoreSession(activeSession);
  }
});
</script>
