<template>
  <div class="left-panel-inner">
    <div class="logo-area">
      <div class="logo-icon">DC</div>
      <h1 class="app-title">Data-Copilot</h1>
      <p class="app-subtitle">Think → Action → Act → Observe</p>
    </div>

    <div class="session-info">
      <span class="label">Session</span>
      <code class="session-id">{{ sessionId }}</code>
    </div>

    <div class="control-panel">
      <button class="ctrl-btn" @click="$emit('resume-session')" :disabled="isRunning">
        <span class="btn-icon">🔄</span> Resume Session
      </button>
      <button class="ctrl-btn new-session" @click="$emit('new-session')">
        <span class="btn-icon">✨</span> New Chat
      </button>
      <button class="ctrl-btn">
        <span class="btn-icon">🌐</span> Sites
      </button>
      <button class="ctrl-btn">
        <span class="btn-icon">⏰</span> Scheduled
      </button>
      <button class="ctrl-btn">
        <span class="btn-icon">🔌</span> Plugins
      </button>
      <div class="collapsible-section">
        <div class="collapsible-header" @click="pinnedOpen = !pinnedOpen">
          <span class="collapsible-arrow">{{ pinnedOpen ? '▾' : '▸' }}</span>
          Pinned
        </div>
        <div v-show="pinnedOpen" class="collapsible-body"></div>
      </div>
      <div class="collapsible-section">
        <div class="collapsible-header" @click="projectsOpen = !projectsOpen">
          <span class="collapsible-arrow">{{ projectsOpen ? '▾' : '▸' }}</span>
          Projects
        </div>
        <div v-show="projectsOpen" class="collapsible-body"></div>
      </div>
      <div class="collapsible-section">
        <div class="collapsible-header" @click="recentsOpen = !recentsOpen">
          <span class="collapsible-arrow">{{ recentsOpen ? '▾' : '▸' }}</span>
          Recents
        </div>
        <div v-show="recentsOpen" class="collapsible-body"></div>
      </div>
    </div>

    <div class="spacer"></div>

    <div class="options-section" :class="{ 'options-locked': isRunning }">
      <div v-if="isRunning" class="options-locked-hint">
        <span class="locked-dot"></span>
        Running — settings locked
      </div>
      <div class="option-item">
        <label class="option-label">Model</label>
        <select
          class="option-select"
          v-model="configState.current_model"
          :disabled="isRunning"
          @change="onModelChange"
        >
          <option v-for="m in configState.models" :key="m.id" :value="m.id">
            {{ m.name }}
          </option>
        </select>
      </div>
      <div class="option-item">
        <label class="option-label">Depth</label>
        <select
          class="option-select"
          v-model="configState.current_reasoning_effort"
          :disabled="isRunning || reasoningEffortOptions.length === 0"
          @change="onReasoningEffortChange"
        >
          <option v-for="opt in reasoningEffortOptions" :key="opt" :value="opt">
            {{ opt }}
          </option>
          <option value="">Default</option>
        </select>
      </div>
      <div class="option-item">
        <label class="option-label">Style</label>
        <select
          class="option-select"
          v-model="configState.current_style"
          :disabled="isRunning || styleOptions.length === 0"
          @change="onStyleChange"
        >
          <option v-for="opt in styleOptions" :key="opt" :value="opt">
            {{ opt }}
          </option>
          <option value="">Default</option>
        </select>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { configState, selectModel, selectReasoningEffort, selectStyle, restoreSavedModel } from '@/utils/config.js'

defineProps({
  sessionId: { type: String, required: true },
  isRunning: { type: Boolean, default: false },
  serverUrl: { type: String, default: window.location.origin },
})

defineEmits(['resume-session', 'new-session'])

const pinnedOpen = ref(false)
const projectsOpen = ref(false)
const recentsOpen = ref(false)

const reasoningEffortOptions = computed(() => {
  const model = configState.models.find(m => m.id === configState.current_model)
  return Array.isArray(model?.reasoning_effort_options) ? model.reasoning_effort_options : []
})

const styleOptions = computed(() => {
  const model = configState.models.find(m => m.id === configState.current_model)
  return Array.isArray(model?.style_options) ? model.style_options : []
})

function onModelChange() {
  selectModel(configState.current_model)
}

function onReasoningEffortChange() {
  selectReasoningEffort(configState.current_reasoning_effort)
}

function onStyleChange() {
  selectStyle(configState.current_style)
}

onMounted(async () => {
  await restoreSavedModel()
})
</script>

<style scoped>
.spacer {
  flex: 1;
  min-height: 0;
}

.options-section {
  border-top: 1px solid var(--border-color);
  padding-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex-shrink: 0;
}

.option-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.option-label {
  font-size: 11px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.option-select {
  padding: 6px 8px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: 12px;
  outline: none;
  cursor: pointer;
  transition: border-color 0.2s;
}

.option-select:hover,
.option-select:focus {
  border-color: var(--accent-blue);
}

.option-select:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  border-style: dashed;
  color: var(--text-muted);
}

.option-select:disabled:hover {
  border-color: var(--border-color);
}

.options-locked .option-label {
  opacity: 0.55;
}

.options-locked-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 2px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.3px;
  color: #f0b429;
}

.locked-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #f0b429;
  flex-shrink: 0;
  animation: locked-pulse 1.2s ease-in-out infinite;
}

@keyframes locked-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.25;
  }
}

.collapsible-section {
  flex-shrink: 0;
}

.collapsible-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 6px 0;
  cursor: pointer;
  user-select: none;
}

.collapsible-header:hover {
  color: var(--text-primary);
}

.collapsible-arrow {
  font-size: 10px;
  width: 12px;
  flex-shrink: 0;
}

.collapsible-body {
  padding: 0;
}
</style>