<template>
  <div class="chat-layout" :class="{ 'hide-conversations': conversationsCollapsed, 'hide-profile': profileCollapsed }">
    <aside v-if="!conversationsCollapsed" class="conversation-panel">
      <div class="conversation-head">
        <div>
          <h2>对话</h2>
          <p>{{ conversations.length }} 个窗口</p>
        </div>
        <div class="conversation-tools">
          <button class="icon-button ghost" type="button" title="隐藏对话列表" @click="setConversationsCollapsed(true)">‹</button>
          <button class="icon-button" type="button" title="新建对话" @click="newConversation">＋</button>
        </div>
      </div>

      <div class="conversation-list">
        <button
          v-for="conversation in conversations"
          :key="conversation.id"
          class="conversation-item"
          :class="{ active: conversation.id === activeConversationId }"
          type="button"
          @click="selectConversation(conversation.id)"
        >
          <span class="conversation-title">{{ conversation.title || '新的对话' }}</span>
          <span class="conversation-meta">
            {{ conversation.messages.length }} 条
            <em v-if="conversation.answering">生成中</em>
          </span>
        </button>
      </div>
    </aside>
    <button
      v-else
      class="sidebar-restore left"
      type="button"
      title="显示对话列表"
      @click="setConversationsCollapsed(false)"
    >
      对话
    </button>

    <section class="chat-panel">
      <div class="page-head compact">
        <div>
          <h1>{{ activeConversation?.title || '知识库问答' }}</h1>
          <p>基于本地文档、长期记忆和学习画像回答问题。</p>
        </div>
        <div class="head-actions">
          <label class="model-picker">
            <span>模型</span>
            <select v-model="selectedChatModel" :disabled="answering" @change="setSelectedChatModel(selectedChatModel)">
              <option v-for="model in chatModels" :key="model" :value="model">{{ model }}</option>
            </select>
          </label>
          <div class="action-menu">
            <span class="menu-trigger" tabindex="0">视图</span>
            <div class="menu-popover">
              <button type="button" @click="setConversationsCollapsed(!conversationsCollapsed)">
                {{ conversationsCollapsed ? '显示对话列表' : '隐藏对话列表' }}
              </button>
              <button type="button" @click="setProfileCollapsed(!profileCollapsed)">
                {{ profileCollapsed ? '显示学习画像' : '隐藏学习画像' }}
              </button>
            </div>
          </div>
          <div class="action-menu">
            <span class="menu-trigger" tabindex="0">对话操作</span>
            <div class="menu-popover">
              <button type="button" title="修改当前对话窗口在左侧列表中的名称" @click="renameCurrent">
                重命名窗口
              </button>
              <button type="button" :disabled="messages.length === 0" @click="clearChatHistory">
                清空当前对话
              </button>
              <button type="button" class="danger-text" @click="deleteCurrentConversation">
                删除窗口
              </button>
              <button type="button" class="danger-text" :disabled="anyConversationAnswering" @click="clearAllHistory">
                清空所有历史
              </button>
            </div>
          </div>
        </div>
      </div>

      <div class="messages">
        <div v-if="messages.length === 0 && !answering" class="empty chat-empty">
          在当前对话里提出一个问题。你可以新建多个窗口，把不同主题分开整理。
        </div>
        <div v-for="(msg, index) in messages" :key="`${msg.requestId || 'msg'}-${index}`" class="message" :class="msg.role">
          <MarkdownView :text="msg.content" />
          <div v-if="msg.learningInsight" class="insight">
            <b>学习诊断</b>
            <p>{{ msg.learningInsight.summary || '已记录本轮学习状态。' }}</p>
          </div>
          <div v-if="msg.followups?.length" class="followups">
            <button v-for="item in msg.followups" :key="item" type="button" :disabled="answering" @click="send(item)">
              {{ item }}
            </button>
          </div>
          <div v-if="msg.chunks?.length" class="citations">
            <button v-for="chunk in msg.chunks" :key="chunk.source + chunk.page + chunk.distance" type="button" @click="selectedChunk = chunk">
              {{ chunk.source }} <span v-if="chunk.page > 0">P{{ chunk.page }}</span>
            </button>
          </div>
          <button v-if="msg.role === 'bot'" class="message-delete" type="button" @click="deleteMessageGroup(index)">
            删除本组问答
          </button>
        </div>
        <div v-if="answering" class="message bot thinking">检索和思考中...</div>
      </div>

      <form class="composer" @submit.prevent="send()">
        <input v-model="input" :placeholder="composerPlaceholder" :disabled="answering" />
        <button :disabled="answering || !input.trim()">发送</button>
      </form>
    </section>

    <ProfilePanel
      v-if="!profileCollapsed"
      :profile="profile"
      :loading="profileLoading"
      :error="profileError"
      :cached-at="profileCachedAt"
      @refresh="loadProfile"
      @review="goReview"
      @delete-tag="deleteProfileTag"
    />
    <button
      v-else
      class="sidebar-restore right"
      type="button"
      title="显示学习画像"
      @click="setProfileCollapsed(false)"
    >
      画像
    </button>
    <CitationViewer :chunk="selectedChunk" @close="selectedChunk = null" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { chatStore } from '../chatStore';
import MarkdownView from '../components/MarkdownView.vue';
import ProfilePanel from '../components/ProfilePanel.vue';
import CitationViewer from '../components/CitationViewer.vue';

const router = useRouter();
const route = useRoute();
const input = ref('');
const selectedChunk = ref<any>(null);
const conversationsCollapsedKey = 'local_rag_conversations_collapsed';
const profileCollapsedKey = 'local_rag_profile_collapsed';
const conversationsCollapsed = ref(localStorage.getItem(conversationsCollapsedKey) === '1');
const profileCollapsed = ref(localStorage.getItem(profileCollapsedKey) === '1');

const conversations = chatStore.conversations;
const activeConversationId = chatStore.activeConversationId;
const activeConversation = chatStore.activeConversation;
const messages = chatStore.messages;
const answering = chatStore.answering;
const anyConversationAnswering = chatStore.anyConversationAnswering;
const activeAnswerCount = chatStore.activeAnswerCount;
const profile = chatStore.profile;
const profileLoading = chatStore.profileLoading;
const profileError = chatStore.profileError;
const profileCachedAt = chatStore.profileCachedAt;
const chatModels = chatStore.chatModels;
const selectedChatModel = chatStore.selectedChatModel;
const setSelectedChatModel = chatStore.setSelectedChatModel;
const composerPlaceholder = computed(() => {
  if (answering.value) return '当前对话正在生成回答...';
  if (activeAnswerCount.value > 0) return `已有 ${activeAnswerCount.value} 个对话正在生成，当前窗口仍可提问`;
  return '向知识库提问...';
});

function setConversationsCollapsed(collapsed: boolean) {
  conversationsCollapsed.value = collapsed;
  localStorage.setItem(conversationsCollapsedKey, collapsed ? '1' : '0');
}

function setProfileCollapsed(collapsed: boolean) {
  profileCollapsed.value = collapsed;
  localStorage.setItem(profileCollapsedKey, collapsed ? '1' : '0');
}

function newConversation() {
  selectedChunk.value = null;
  const id = chatStore.createConversation();
  router.replace(`/chat/${id}`);
}

function selectConversation(id: string) {
  selectedChunk.value = null;
  chatStore.selectConversation(id);
  router.replace(`/chat/${id}`);
}

function renameCurrent() {
  const current = activeConversation.value;
  if (!current) return;
  const title = prompt('请输入对话名称', current.title || '新的对话');
  if (title === null) return;
  chatStore.renameConversation(current.id, title);
}

function deleteCurrentConversation() {
  const current = activeConversation.value;
  if (!current) return;
  if (!confirm(`确定要删除“${current.title || '新的对话'}”吗？`)) return;
  selectedChunk.value = null;
  chatStore.deleteConversation(current.id);
}

async function clearChatHistory() {
  if (!confirm('确定要清空当前对话吗？学习画像和长期记忆不会被删除。')) return;
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

watch(
  () => route.params.conversationId,
  (id) => {
    if (typeof id === 'string' && id && id !== activeConversationId.value) {
      chatStore.selectConversation(id);
    }
  },
  { immediate: true },
);

watch(activeConversationId, (id) => {
  if (id && route.params.conversationId !== id) {
    router.replace(`/chat/${id}`);
  }
});
</script>
