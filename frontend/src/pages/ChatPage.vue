<template>
  <div class="chat-layout">
    <section class="chat-panel">
      <div class="page-head">
        <div>
          <h1>知识库问答</h1>
          <p>基于本地文档、长期记忆和学习画像回答问题。</p>
        </div>
        <div class="head-actions">
          <label class="model-picker">
            <span>模型</span>
            <select v-model="selectedChatModel" :disabled="answering" @change="setSelectedChatModel(selectedChatModel)">
              <option v-for="model in chatModels" :key="model" :value="model">{{ model }}</option>
            </select>
          </label>
          <button class="button danger ghost" :disabled="answering || messages.length === 0" @click="clearChatHistory">
            删除问答历史
          </button>
          <button class="button danger ghost" :disabled="answering" @click="clearAllHistory">
            清空所有历史
          </button>
          <RouterLink class="button ghost" to="/knowledge">管理知识库</RouterLink>
        </div>
      </div>

      <div class="messages">
        <div v-for="(msg, index) in messages" :key="index" class="message" :class="msg.role">
          <MarkdownView :text="msg.content" />
          <div v-if="msg.learningInsight" class="insight">
            <b>学习诊断</b>
            <p>{{ msg.learningInsight.summary || '已记录本轮学习状态。' }}</p>
          </div>
          <div v-if="msg.followups?.length" class="followups">
            <button v-for="item in msg.followups" :key="item" @click="send(item)">{{ item }}</button>
          </div>
          <div v-if="msg.chunks?.length" class="citations">
            <button v-for="chunk in msg.chunks" :key="chunk.source + chunk.page + chunk.distance" @click="selectedChunk = chunk">
              {{ chunk.source }} <span v-if="chunk.page > 0">P{{ chunk.page }}</span>
            </button>
          </div>
          <button v-if="msg.role === 'bot'" class="message-delete" @click="deleteMessageGroup(index)">
            删除本组问答
          </button>
        </div>
        <div v-if="answering" class="message bot">检索和思考中...</div>
      </div>

      <form class="composer" @submit.prevent="send()">
        <input v-model="input" placeholder="向知识库提问..." />
        <button :disabled="answering || !input.trim()">发送</button>
      </form>
    </section>

    <ProfilePanel
      :profile="profile"
      :loading="profileLoading"
      :error="profileError"
      :cached-at="profileCachedAt"
      @refresh="loadProfile"
      @review="goReview"
      @delete-tag="deleteProfileTag"
    />
    <CitationViewer :chunk="selectedChunk" @close="selectedChunk = null" />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { chatStore } from '../chatStore';
import MarkdownView from '../components/MarkdownView.vue';
import ProfilePanel from '../components/ProfilePanel.vue';
import CitationViewer from '../components/CitationViewer.vue';

const router = useRouter();
const input = ref('');
const selectedChunk = ref<any>(null);

async function clearChatHistory() {
  if (!confirm('确定要删除当前用户的本地问答历史吗？学习画像和长期记忆不会被删除。')) return;
  selectedChunk.value = null;
  await chatStore.clearChatHistory();
}

async function clearAllHistory() {
  const ok = confirm('确定要彻底清空当前用户的所有历史吗？这会删除问答历史、用户画像、学习计划和学习历史，但不会清空知识库。');
  if (!ok) return;
  selectedChunk.value = null;
  await chatStore.clearAllHistory();
  alert('已清空所有用户历史，知识库未受影响。');
}

async function deleteMessageGroup(index: number) {
  await chatStore.deleteMessageGroup(index);
}

async function loadProfile() {
  await chatStore.loadProfile();
}

async function send(preset?: string) {
  const question = (preset || input.value).trim();
  if (!question) return;
  input.value = '';
  await chatStore.sendQuestion(question);
}

function goReview(item: any) {
  router.push({ path: '/review', query: { topic: item.name, score: item.score || 0 } });
}

async function deleteProfileTag(item: { category: string; value: string }) {
  await chatStore.deleteProfileTag(item);
}

const messages = chatStore.messages;
const answering = chatStore.answering;
const profile = chatStore.profile;
const profileLoading = chatStore.profileLoading;
const profileError = chatStore.profileError;
const profileCachedAt = chatStore.profileCachedAt;
const chatModels = chatStore.chatModels;
const selectedChatModel = chatStore.selectedChatModel;
const setSelectedChatModel = chatStore.setSelectedChatModel;
</script>
