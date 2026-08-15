<template>
  <div class="chat-container">
    <div class="messages-area" ref="messagesContainer">
      <div v-if="messages.length === 0 && !isRunning" class="empty-state">
        <div class="empty-icon">💬</div>
        <h2>Data-Copilot v4</h2>
        <p>Ask a question to start analyzing your data</p>
      </div>

      <MessageItem
        v-for="msg in messages"
        :key="msg.id"
        :message="msg"
      />

      <div v-if="isRunning" class="thinking-indicator">
        <span class="blink-cursor">|</span>
        <span class="thinking-text">Thinking...</span>
      </div>
    </div>

    <div class="input-area">
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
        <div class="question-input-row">
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
            :disabled="isRunning || !currentQuestion.trim()"
            @click="onSubmitQuestion"
          >Send</button>
        </div>
        <div class="context-info-row">
          <div class="context-info-label">ICP 赔案号 · 附加说明</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick, onMounted } from 'vue'
import MessageItem from '@/components/MessageItem.vue'

const props = defineProps({
  chat: { type: Object, required: true },
})

const {
  messages, isRunning, isCompleted, isPaused,
  awaitingInput, inputPrompt, inputChoices,
  startChat, submitUserResponse, submitPausedInput, submitNewQuestion,
} = props.chat

const currentQuestion = ref('')
const userInput = ref('')
const pausedInput = ref('')
const messagesContainer = ref(null)
const userInputRef = ref(null)

function onSubmitQuestion() {
  const q = currentQuestion.value.trim()
  if (!q || isRunning.value) return
  if (isCompleted.value) {
    submitNewQuestion(q)
  } else {
    startChat(q)
  }
  currentQuestion.value = ''
}

function onUserResponse(text) {
  const t = text?.trim?.() || text
  if (!t) return
  submitUserResponse(t)
  userInput.value = ''
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
  await nextTick()
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}, { deep: true })
</script>