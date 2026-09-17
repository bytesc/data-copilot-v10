import { createRouter, createWebHistory } from 'vue-router'
import ChatPage from '@/pages/ChatPage.vue'
import DataPage from '@/pages/DataPage.vue'
import BaseKnowledgePage from '@/pages/BaseKnowledgePage.vue'
import DataQueryGuidePage from '@/pages/DataQueryGuidePage.vue'

const routes = [
  { path: '/', name: 'chat', component: ChatPage },
  { path: '/data', name: 'data', component: DataPage },
  { path: '/base-knowledge', name: 'base-knowledge', component: BaseKnowledgePage },
  { path: '/data-query-guide', name: 'data-query-guide', component: DataQueryGuidePage },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router