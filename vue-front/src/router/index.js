import { createRouter, createWebHistory } from 'vue-router'
import ChatPage from '@/pages/ChatPage.vue'
import DataPage from '@/pages/DataPage.vue'
import DataUploadPage from '@/pages/DataUploadPage.vue'
import BaseKnowledgePage from '@/pages/BaseKnowledgePage.vue'
import DataQueryGuidePage from '@/pages/DataQueryGuidePage.vue'
import BriefInfoPage from '@/pages/BriefInfoPage.vue'
import CommentManagePage from '@/pages/CommentManagePage.vue'
import GuideManagePage from '@/pages/GuideManagePage.vue'
import ToolsPage from '@/pages/ToolsPage.vue'
import KnowledgePage from '@/pages/KnowledgePage.vue'

const routes = [
  { path: '/', name: 'chat', component: ChatPage },
  { path: '/tools', name: 'tools', component: ToolsPage },
  {
    path: '/data',
    component: DataPage,
    children: [
      { path: '', name: 'data-upload', component: DataUploadPage },
      { path: 'comments', name: 'comment-manage', component: CommentManagePage },
      { path: 'query-guide', name: 'data-query-guide', component: DataQueryGuidePage },
    ],
  },
  {
    path: '/knowledge',
    component: KnowledgePage,
    children: [
      { path: '', name: 'knowledge-redirect', redirect: '/knowledge/base-knowledge' },
      { path: 'base-knowledge', name: 'base-knowledge', component: BaseKnowledgePage },
      { path: 'brief-info', name: 'brief-info', component: BriefInfoPage },
      { path: 'guides', name: 'guide-manage', component: GuideManagePage },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router