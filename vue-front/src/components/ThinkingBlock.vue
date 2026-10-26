<template>
  <details v-if="message.thinking" class="msg-collapse thinking-block">
    <summary class="collapse-summary">
      <span class="thinking-summary-label">思考过程</span>
      <span v-if="message.thinkingStreaming" class="blink-cursor">|</span>
    </summary>
    <div class="collapse-body thinking-content" v-html="renderMd(message.thinking)"></div>
  </details>
</template>

<script setup>
import { renderMarkdown } from '@/utils/markdown.js'

const props = defineProps({
  message: { type: Object, required: true },
})

function renderMd(text) {
  return renderMarkdown(text || '')
}
</script>

<style scoped>
.thinking-content {
  color: var(--text-muted);
  font-style: italic;
  font-size: 13px;
  max-height: 300px;
  overflow-y: auto;
}
.thinking-summary-label {
  color: var(--text-muted);
}
</style>
