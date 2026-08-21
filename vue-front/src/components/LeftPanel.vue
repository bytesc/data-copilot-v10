<template>
  <div class="left-panel-inner">
    <div class="logo-area">
      <div class="logo-icon">DC</div>
      <h1 class="app-title">Data-Copilot v10</h1>
      <p class="app-subtitle">Think → Action → Act → Observe</p>
    </div>

    <div class="session-info">
      <span class="label">Session</span>
      <code class="session-id">{{ sessionId }}</code>
    </div>

    <div class="control-panel">
      <button class="ctrl-btn" @click="$emit('upload-csv')" :disabled="isRunning">
        <span class="btn-icon">📄</span> Upload CSV
      </button>
      <button class="ctrl-btn" @click="$emit('upload-doc')" :disabled="isRunning">
        <span class="btn-icon">📝</span> Upload Document
      </button>
      <button class="ctrl-btn" @click="$emit('resume-session')" :disabled="isRunning">
        <span class="btn-icon">🔄</span> Resume Session
      </button>
      <button class="ctrl-btn" @click="$emit('generate-doc')" :disabled="isRunning">
        <span class="btn-icon">📋</span> Generate Summary
      </button>
      <button class="ctrl-btn new-session" @click="$emit('new-session')">
        <span class="btn-icon">✨</span> New Session
      </button>
    </div>

    <DbOverview :server-url="serverUrl" />
  </div>
</template>

<script setup>
import DbOverview from '@/components/DbOverview.vue'

defineProps({
  sessionId: { type: String, required: true },
  isRunning: { type: Boolean, default: false },
  serverUrl: { type: String, default: 'http://127.0.0.1:8009' },
})

defineEmits(['upload-csv', 'upload-doc', 'resume-session', 'generate-doc', 'new-session'])
</script>