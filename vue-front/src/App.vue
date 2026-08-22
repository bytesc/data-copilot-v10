<template>
  <div class="app-container">
    <div class="content-row">
<aside class="left-panel" :class="{ collapsed: isPanelCollapsed }">
          <div class="panel-toggle" @click="isPanelCollapsed = !isPanelCollapsed">
            {{ isPanelCollapsed ? '▶' : '◀' }}
          </div>
          <LeftPanel
            v-if="!isPanelCollapsed"
            :session-id="chat.sessionId.value"
            :is-running="chat.isRunning.value"
            :server-url="chat.serverUrl.value"
            @upload-csv="showUploadCsv = true"
            @upload-doc="showUploadDoc = true"
            @resume-session="showResume = true"
            @generate-doc="chat.generateDocument()"
            @generate-doc-unified="chat.generateDocumentUnified()"
            @new-session="chat.reset()"
          />
        </aside>
      <main class="chat-area">
        <ChatArea :chat="chat" />
      </main>
<aside class="right-panel" :class="{ collapsed: isRightPanelCollapsed }">
          <div class="panel-toggle right" @click="isRightPanelCollapsed = !isRightPanelCollapsed">
            {{ isRightPanelCollapsed ? '◀' : '▶' }}
          </div>
          <RightPanel v-if="!isRightPanelCollapsed" :files="chat.generatedFiles.value" />
        </aside>
    </div>
    <IcpArea />

    <button class="theme-toggle" :title="isDark ? '切换到亮色主题' : '切换到暗色主题'" @click="toggleTheme">
      <svg v-if="isDark" viewBox="0 0 24 24">
        <circle cx="12" cy="12" r="4"></circle>
        <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"></path>
      </svg>
      <svg v-else viewBox="0 0 24 24">
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
      </svg>
    </button>

    <UploadModal
      v-if="showUploadCsv"
      type="csv"
      :server-url="chat.serverUrl.value"
      @close="showUploadCsv = false"
    />
    <UploadModal
      v-if="showUploadDoc"
      type="doc"
      :server-url="chat.serverUrl.value"
      @close="showUploadDoc = false"
    />
    <ResumeModal
      v-if="showResume"
      :server-url="chat.serverUrl.value"
      @close="showResume = false"
      @resume="onResume"
    />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useChat } from '@/composables/useChat.js'
import LeftPanel from '@/components/LeftPanel.vue'
import RightPanel from '@/components/RightPanel.vue'
import ChatArea from '@/components/ChatArea.vue'
import IcpArea from '@/components/IcpArea.vue'
import UploadModal from '@/components/UploadModal.vue'
import ResumeModal from '@/components/ResumeModal.vue'

const chat = useChat()
const isPanelCollapsed = ref(false)
const isRightPanelCollapsed = ref(false)
const showUploadCsv = ref(false)
const showUploadDoc = ref(false)
const showResume = ref(false)

const isDark = ref(true)

function applyTheme() {
  const theme = isDark.value ? 'dark' : 'light'
  document.documentElement.setAttribute('data-theme', theme)
  localStorage.setItem('theme', theme)
}

function toggleTheme() {
  isDark.value = !isDark.value
  applyTheme()
}

onMounted(() => {
  const saved = localStorage.getItem('theme')
  isDark.value = saved !== 'light'
  applyTheme()
})

function onResume(sessionData) {
  showResume.value = false
  chat.resumeSession(sessionData)
}
</script>