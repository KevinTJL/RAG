import { createRouter, createWebHistory } from 'vue-router';
import ChatPage from './pages/ChatPage.vue';
import GuidePage from './pages/GuidePage.vue';
import KnowledgePage from './pages/KnowledgePage.vue';
import ReviewPage from './pages/ReviewPage.vue';
import LearningHistoryPage from './pages/LearningHistoryPage.vue';

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/chat' },
    { path: '/guide', component: GuidePage },
    { path: '/chat', component: ChatPage },
    { path: '/knowledge', component: KnowledgePage },
    { path: '/review', component: ReviewPage },
    { path: '/learning-history', component: LearningHistoryPage },
  ],
});
