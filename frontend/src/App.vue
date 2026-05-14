<template>
  <div v-if="!user" class="auth-screen">
    <form class="auth-panel" @submit.prevent="submitAuth">
      <h1>Local RAG</h1>
      <p>登录后使用个人知识库、问答和学习计划。</p>
      <input v-model="email" type="email" placeholder="邮箱" autocomplete="email" />
      <input v-model="password" type="password" placeholder="密码（至少 8 位）" autocomplete="current-password" />
      <div v-if="error" class="error small">{{ error }}</div>
      <button :disabled="loading || !email || !password">{{ loading ? '处理中...' : authMode === 'login' ? '登录' : '注册' }}</button>
      <button class="ghost" type="button" :disabled="loading" @click="toggleMode">
        {{ authMode === 'login' ? '没有账号？注册' : '已有账号？登录' }}
      </button>
    </form>
  </div>

  <div v-else class="shell">
    <aside class="nav">
      <div>
        <div class="brand">Local RAG</div>
        <div class="user">{{ user.email }}</div>
      </div>
      <nav>
        <RouterLink to="/guide">说明</RouterLink>
        <RouterLink to="/chat">问答</RouterLink>
        <RouterLink to="/knowledge">知识库</RouterLink>
        <RouterLink to="/review">学习计划</RouterLink>
        <RouterLink to="/learning-history">学习历史</RouterLink>
        <button class="nav-logout" type="button" @click="logout">退出登录</button>
      </nav>
    </aside>
    <main class="main">
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, watchEffect } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { authStore } from './authStore';
import { hasSeenGuide } from './onboarding';

const user = authStore.user;
const loading = authStore.loading;
const error = authStore.error;
const route = useRoute();
const router = useRouter();
const email = ref('');
const password = ref('');
const authMode = ref<'login' | 'register'>('login');

watchEffect(() => {
  if (user.value && !hasSeenGuide(user.value) && route.path !== '/guide') {
    router.replace('/guide');
  }
});

function toggleMode() {
  error.value = '';
  authMode.value = authMode.value === 'login' ? 'register' : 'login';
}

async function submitAuth() {
  if (authMode.value === 'login') {
    await authStore.login(email.value, password.value);
  } else {
    await authStore.register(email.value, password.value);
  }
  window.location.reload();
}

const logout = authStore.logout;
</script>
