<template>
  <div class="app-container">
    <div class="content-row">
      <div class="panel-toggle" @click="isPanelCollapsed = !isPanelCollapsed">
        {{ isPanelCollapsed ? '▶' : '◀' }}
      </div>
      <aside class="left-panel" :class="{ collapsed: isPanelCollapsed }">
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
      <aside class="right-panel" :class="{ collapsed: isRightPanelCollapsed }">
        <RightPanel :files="chat.generatedFiles.value" />
      </aside>
      <div class="panel-toggle right" @click="isRightPanelCollapsed = !isRightPanelCollapsed">
        {{ isRightPanelCollapsed ? '◀' : '▶' }}
      </div>
    </div>
    <IcpArea />

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

function onResume(sessionData) {
  showResume.value = false
  chat.resumeSession(sessionData)
}
</script>