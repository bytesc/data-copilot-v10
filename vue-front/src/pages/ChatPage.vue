<template>
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
import ResumeModal from '@/components/ResumeModal.vue'

const chat = useChat()
const isPanelCollapsed = ref(false)
const isRightPanelCollapsed = ref(false)
const showResume = ref(false)

function onResume(sessionData) {
  showResume.value = false
  chat.resumeSession(sessionData)
}
</script>