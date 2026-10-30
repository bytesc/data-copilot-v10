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
        @new-session="chat.reset()"
      />
    </aside>

    <main class="chat-area">
      <ChatArea ref="chatAreaRef" :chat="chat" />
    </main>

    <aside class="right-panel" :class="{ collapsed: isRightPanelCollapsed }">
      <div class="panel-toggle right" @click="isRightPanelCollapsed = !isRightPanelCollapsed">
        {{ isRightPanelCollapsed ? '◀' : '▶' }}
      </div>
      <RightPanel
        v-if="!isRightPanelCollapsed"
        :files="chat.generatedFiles.value"
        :is-running="chat.isRunning.value || yamlBusy"
        @generate-doc="chat.generateDocumentUnified()"
        @generate-doc-unified="chat.generateDocument()"
        @generate-yaml-doc="onYamlDoc"
      />
    </aside>

    <ResumeModal
      v-if="showResume"
      :server-url="chat.serverUrl.value"
      @close="showResume = false"
      @resume="onResume"
    />
    <YamlOutlineModal
      v-if="showYamlOutline"
      :server-url="chat.serverUrl.value"
      :conversation-history="chat.conversationHistory.value"
      :session-id="chat.sessionId.value"
      @close="showYamlOutline = false"
      @files-updated="chat.generatedFiles.value.push($event)"
      @running="yamlBusy = $event"
      @send-yaml="onSendYaml"
    />
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useChat } from '@/composables/useChat.js'
import LeftPanel from '@/components/LeftPanel.vue'
import RightPanel from '@/components/RightPanel.vue'
import ChatArea from '@/components/ChatArea.vue'
import ResumeModal from '@/components/ResumeModal.vue'
import YamlOutlineModal from '@/components/YamlOutlineModal.vue'

const chatAreaRef = ref(null)
const chat = useChat()

function isMobileViewport() {
  return window.innerWidth <= 768
}

let lastMobile = isMobileViewport()
const isPanelCollapsed = ref(lastMobile)
const isRightPanelCollapsed = ref(lastMobile)
const showResume = ref(false)
const showYamlOutline = ref(false)
const yamlBusy = ref(false)

function syncPanelsWithViewport() {
  const mobile = isMobileViewport()
  if (mobile === lastMobile) return
  lastMobile = mobile
  if (mobile) {
    isPanelCollapsed.value = true
    isRightPanelCollapsed.value = true
  }
}

onMounted(() => {
  window.addEventListener('resize', syncPanelsWithViewport)
})
onUnmounted(() => {
  window.removeEventListener('resize', syncPanelsWithViewport)
})

function onResume(sessionData) {
  showResume.value = false
  chat.resumeSession(sessionData)
}

function onYamlDoc() {
  showYamlOutline.value = true
}

function onSendYaml(yamlContent) {
  showYamlOutline.value = false
  chatAreaRef.value?.setQuestion(yamlContent)
}
</script>