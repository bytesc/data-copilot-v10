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
      <button class="ctrl-btn" @click="$emit('generate-doc')" :disabled="isRunning">
        <span class="btn-icon">📋</span> Generate Summary
      </button>
      <button class="ctrl-btn" @click="$emit('generate-doc-unified')" :disabled="isRunning">
        <span class="btn-icon">📄</span> Generate Full Doc
      </button>
      <button class="ctrl-btn new-session" @click="$emit('new-session')">
        <span class="btn-icon">✨</span> New Session
      </button>
    </div>

    <div class="spacer"></div>

    <div class="options-section">
      <div class="option-item">
        <label class="option-label">Model</label>
        <select class="option-select">
          <option>GPT-4o</option>
          <option>Claude 3.5</option>
          <option selected>deepseek-v4-pro</option>
          <option>deepseek-v4-flash</option>
        </select>
      </div>
      <div class="option-item">
        <label class="option-label">Style</label>
        <select class="option-select">
          <option>Formal</option>
          <option>Casual</option>
          <option>Technical</option>
        </select>
      </div>
      <div class="option-item">
        <label class="option-label">Depth</label>
        <select class="option-select">
          <option>Standard</option>
          <option>Deep</option>
          <option>Maximum</option>
        </select>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  sessionId: { type: String, required: true },
  isRunning: { type: Boolean, default: false },
  serverUrl: { type: String, default: 'http://127.0.0.1:8009' },
})

defineEmits(['resume-session', 'generate-doc', 'generate-doc-unified', 'new-session'])
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
</style>