import { createRouter, createWebHistory } from 'vue-router'
import ChatPage from '@/pages/ChatPage.vue'
import DataPage from '@/pages/DataPage.vue'
import DataUploadPage from '@/pages/DataUploadPage.vue'
import BaseKnowledgePage from '@/pages/BaseKnowledgePage.vue'
import DataQueryGuidePage from '@/pages/DataQueryGuidePage.vue'
import BriefInfoPage from '@/pages/BriefInfoPage.vue'
import CommentManagePage from '@/pages/CommentManagePage.vue'

const routes = [
  { path: '/', name: 'chat', component: ChatPage },
  {
    path: '/data',
    component: DataPage,
    children: [
      { path: '', name: 'data-upload', component: DataUploadPage },
      { path: 'base-knowledge', name: 'base-knowledge', component: BaseKnowledgePage },
      { path: 'query-guide', name: 'data-query-guide', component: DataQueryGuidePage },
      { path: 'brief-info', name: 'brief-info', component: BriefInfoPage },
      { path: 'comments', name: 'comment-manage', component: CommentManagePage },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router