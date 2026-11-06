<template>
  <div class="chat-container">
    <div class="messages-area" ref="messagesContainer">
      <div v-if="messages.length === 0 && !isRunning" class="empty-state">
        <div class="empty-icon">💬</div>
        <h2>Data-Copilot</h2>
        <p>Ask a question to start analyzing your data</p>
      </div>

      <MessageItem
        v-for="msg in messages"
        :key="msg.id"
        :message="msg"
        :server-url="serverUrl"
      />

      <div v-if="isRunning" class="thinking-indicator">
        <div v-if="statusMsg" class="status-msg">{{ statusMsg }}</div>
        <div class="thinking-indicator-row">
          <span class="blink-cursor">|</span>
          <span class="thinking-text">Thinking...</span>
          <button class="interrupt-btn" :disabled="interruptRequested" @click="onInterrupt">{{ interruptRequested ? 'Interrupting...' : 'Interrupt' }}</button>
        </div>
      </div>
    </div>

    <div class="input-area">
      <div class="mode-switch-bar">
        <span class="mode-switch-label">Mode</span>
        <div
          class="mode-switch"
          :class="chatMode"
          :aria-checked="chatMode === 'think'"
          :aria-disabled="isRunning"
          role="switch"
          tabindex="0"
          @click="onToggleMode"
          @keydown.enter.space.prevent="onToggleMode"
        >
          <span class="mode-switch-thumb"></span>
          <span class="mode-switch-option left" :class="{ active: chatMode === 'think' }">Think</span>
          <span class="mode-switch-option right" :class="{ active: chatMode === 'chat' }">Chat</span>
        </div>

        <div
          class="image-switch-group"
          :title="supportsImages ? 'Attach blackboard images to model requests' : 'This model does not support image input'"
        >
          <span class="mode-switch-label">Images</span>
          <button
            class="image-switch"
            :class="{ on: useImages, disabled: !supportsImages }"
            :aria-checked="useImages"
            :aria-disabled="!supportsImages || isRunning"
            :disabled="!supportsImages || isRunning"
            role="switch"
            @click="onToggleImages"
          >
            <span class="image-switch-thumb"></span>
          </button>
        </div>
      </div>

      <div v-if="awaitingInput" class="user-input-prompt">
        <div v-if="inputChoices.length > 0" class="choices-group">
          <p class="input-prompt-text">{{ inputPrompt }}</p>
          <div class="choices-list">
            <button
              v-for="choice in inputChoices"
              :key="choice"
              class="choice-btn"
              @click="onUserResponse(choice)"
            >{{ choice }}</button>
          </div>
        </div>
        <div v-else class="text-input-group">
          <p class="input-prompt-text">{{ inputPrompt }}</p>
          <textarea
            ref="userInputRef"
            v-model="userInput"
            class="user-input-textarea"
            rows="2"
            placeholder="Type your response..."
            @keydown.enter.exact.prevent="onUserResponse(userInput)"
          ></textarea>
          <button class="send-btn" @click="onUserResponse(userInput)">Send</button>
        </div>
      </div>

      <div v-else-if="isPaused" class="paused-prompt">
        <p class="paused-text">Paused. Enter a new instruction or click Continue.</p>
        <div class="paused-input-row">
          <textarea
            v-model="pausedInput"
            class="user-input-textarea"
            rows="2"
            placeholder="continue"
            @keydown.enter.exact.prevent="onPausedSubmit"
          ></textarea>
          <button class="send-btn" @click="onPausedSubmit">Continue</button>
        </div>
      </div>

      <div v-else class="question-input-area">
        <div v-if="pendingImages.length || uploadingImages" class="upload-preview-bar">
          <div
            v-for="(img, i) in pendingImages"
            :key="img.previewUrl"
            class="upload-preview-item"
          >
            <img :src="img.previewUrl" :alt="img.name" />
            <button
              class="upload-preview-remove"
              type="button"
              :disabled="isRunning"
              @click="removeUploadImage(i)"
            >✕</button>
          </div>
          <span v-if="uploadingImages" class="upload-preview-status">Uploading...</span>
        </div>
        <div class="question-input-row">
          <button
            class="attach-btn"
            type="button"
            :disabled="isRunning || uploadingImages || pendingImages.length >= MAX_UPLOAD_IMAGES"
            :title="`Upload up to ${MAX_UPLOAD_IMAGES} images`"
            @click="onPickImages"
          >
            <span class="attach-icon">🖼</span>
            <span class="attach-count">{{ pendingImages.length }}/{{ MAX_UPLOAD_IMAGES }}</span>
          </button>
          <textarea
            v-model="currentQuestion"
            class="question-textarea"
            rows="4"
            :placeholder="isCompleted ? 'What is next?' : 'Enter your question here...'"
            :disabled="isRunning"
            @keydown.ctrl.enter.prevent="onSubmitQuestion"
          ></textarea>
          <button
            class="send-btn"
            :disabled="isRunning || uploadingImages || !currentQuestion.trim()"
            @click="onSubmitQuestion"
          >Send</button>
        </div>
        <input
          ref="imageInputRef"
          class="hidden-file-input"
          type="file"
          accept="image/*"
          multiple
          @change="onImagesSelected"
        />
      </div>

      </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import MessageItem from '@/components/MessageItem.vue'
import { configState, selectUseImages } from '@/utils/config.js'

const props = defineProps({
  chat: { type: Object, required: true },
})

const {
  messages, isRunning, isCompleted, isPaused,
  awaitingInput, inputPrompt, inputChoices, serverUrl,
  startChat, submitUserResponse, submitPausedInput, submitNewQuestion,
  requestInterrupt,
  interruptRequested,
  statusMsg,
  chatMode,
  pendingImages, uploadingImages, MAX_UPLOAD_IMAGES,
  addUploadImages, removeUploadImage,
} = props.chat

const currentQuestion = ref('')
const userInput = ref('')
const pausedInput = ref('')
const messagesContainer = ref(null)
const userInputRef = ref(null)
const imageInputRef = ref(null)

const useImages = computed(() => configState.use_images)
const supportsImages = computed(() => {
  const model = configState.models.find(m => m.id === configState.current_model)
  return !!model?.supports_images
})

function onToggleImages() {
  if (isRunning.value || !supportsImages.value) return
  selectUseImages(!configState.use_images)
}

function setMode(mode) {
  chatMode.value = mode
}

function onToggleMode() {
  if (isRunning.value) return
  chatMode.value = chatMode.value === 'think' ? 'chat' : 'think'
}

function setQuestion(text) {
  currentQuestion.value = text
}
defineExpose({ setQuestion })

async function onSubmitQuestion() {
  const q = currentQuestion.value.trim()
  if (!q || isRunning.value || uploadingImages.value) return
  const ok = isCompleted.value
    ? await submitNewQuestion(q)
    : await startChat(q)
  if (ok) currentQuestion.value = ''
}

function onPickImages() {
  if (isRunning.value || uploadingImages.value) return
  imageInputRef.value?.click()
}

function onImagesSelected(event) {
  const input = event.target
  const files = Array.from(input.files || [])
  input.value = ''
  if (files.length === 0) return
  addUploadImages(files)
}

function onUserResponse(text) {
  const t = text?.trim?.() || text
  if (!t) return
  submitUserResponse(t)
  userInput.value = ''
}

function onInterrupt() {
  requestInterrupt()
}

function onPausedSubmit() {
  const input = pausedInput.value.trim()
  submitPausedInput(input)
  pausedInput.value = ''
}

watch(awaitingInput, async (val) => {
  if (val) {
    await nextTick()
    userInputRef.value?.focus()
  }
})

watch(messages, async () => {
  if (_isAnyStreaming()) return
  await nextTick()
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}, { deep: true })

function _isAnyStreaming() {
  return messages.value.some(m => m.streaming)
}
</script>