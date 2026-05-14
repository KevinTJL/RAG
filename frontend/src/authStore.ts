import { ref } from 'vue';
import { api, clearAuthSession, getAuthToken, getAuthUser, setAuthSession, type AuthUser } from './api';

const user = ref<AuthUser | null>(getAuthUser());
const token = ref(getAuthToken());
const loading = ref(false);
const error = ref('');

async function login(email: string, password: string) {
  loading.value = true;
  error.value = '';
  try {
    const data = await api.login({ email, password });
    setAuthSession(data.token, data.user);
    user.value = data.user;
    token.value = data.token;
  } catch (e: any) {
    error.value = e?.message || '登录失败';
    throw e;
  } finally {
    loading.value = false;
  }
}

async function register(email: string, password: string) {
  loading.value = true;
  error.value = '';
  try {
    const data = await api.register({ email, password });
    setAuthSession(data.token, data.user);
    user.value = data.user;
    token.value = data.token;
  } catch (e: any) {
    error.value = e?.message || '注册失败';
    throw e;
  } finally {
    loading.value = false;
  }
}

function logout() {
  clearAuthSession();
  user.value = null;
  token.value = '';
  window.location.reload();
}

export const authStore = {
  user,
  token,
  loading,
  error,
  login,
  register,
  logout,
};
