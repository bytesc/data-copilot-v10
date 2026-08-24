<template>
  <div class="right-panel-inner">
    <div class="doc-section">
      <span class="section-label">Document</span>
      <button class="ctrl-btn" @click="$emit('generate-doc')" :disabled="isRunning">
        <span class="btn-icon">📋</span> Generate Document
      </button>
      <button class="ctrl-btn" @click="$emit('generate-doc-unified')" :disabled="isRunning">
        <span class="btn-icon">📄</span> Generate Report
      </button>
    </div>

    <div class="right-panel-divider"></div>

    <div class="right-panel-header">Generated Files</div>
    <div v-if="files.length === 0" class="right-panel-empty">No files generated yet</div>
    <div v-else class="file-list">
      <div v-for="file in files" :key="file.id" class="file-item">
        <div class="file-title" :title="file.title">{{ file.title }}</div>
        <div class="file-actions">
          <a v-if="file.downloadUrlMd" :href="file.downloadUrlMd + '?download=1'" class="download-btn md" target="_blank">.md</a>
          <a v-if="file.downloadUrlDocx" :href="file.downloadUrlDocx + '?download=1'" class="download-btn docx" target="_blank">.docx</a>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  files: { type: Array, required: true },
  isRunning: { type: Boolean, default: false },
})

defineEmits(['generate-doc', 'generate-doc-unified'])
</script>

<style scoped>
.doc-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 0 16px;
}

.section-label {
  font-size: 11px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 2px;
}

.ctrl-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.ctrl-btn:hover:not(:disabled) {
  background: var(--bg-hover);
  border-color: var(--accent-blue);
}

.ctrl-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-icon {
  font-size: 14px;
}

.right-panel-divider {
  height: 1px;
  background: var(--border-color);
  margin: 12px 16px;
}
</style>