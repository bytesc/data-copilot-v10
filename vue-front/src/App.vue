<template>
  <div class="app-container">
    <aside class="left-panel" :class="{ collapsed: isPanelCollapsed }">
      <div class="panel-toggle" @click="isPanelCollapsed = !isPanelCollapsed">
        {{ isPanelCollapsed ? '▶' : '◀' }}
      </div>
      <LeftPanel
        :session-id="chat.sessionId.value"
        :is-running="chat.isRunning.value"
        :server-url="chat.serverUrl.value"
        @upload-csv="showUploadCsv = true"
        @upload-doc="showUploadDoc = true"
        @resume-session="showResume = true"
        @generate-doc="chat.generateDocument()"
        @new-session="chat.reset()"
      />
    </aside>
    <main class="chat-area">
      <ChatArea :chat="chat" />
    </main>

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
import { ref } from 'vue'
import { useChat } from '@/composables/useChat.js'
import LeftPanel from '@/components/LeftPanel.vue'
import ChatArea from '@/components/ChatArea.vue'
import UploadModal from '@/components/UploadModal.vue'
import ResumeModal from '@/components/ResumeModal.vue'

const chat = useChat()
const isPanelCollapsed = ref(false)
const showUploadCsv = ref(false)
const showUploadDoc = ref(false)
const showResume = ref(false)

function onResume(sessionData) {
  showResume.value = false
  chat.resumeSession(sessionData)
}
</script>