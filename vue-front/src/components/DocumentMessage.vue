<template>
  <div class="document-message">
    <details v-if="message.docOutline" class="msg-collapse">
      <summary class="collapse-summary">Document Outline</summary>
      <div class="collapse-body">
        <p><strong>Title:</strong> {{ message.docOutline.title || '' }}</p>
        <p><strong>Parts:</strong> {{ message.docOutline.parts?.length || 0 }}</p>
        <ol>
          <li v-for="(part, i) in message.docOutline.parts" :key="i">
            <strong>{{ part.heading || `Part ${i + 1}` }}</strong><span v-if="part.description"> — {{ part.description }}</span>
          </li>
        </ol>
      </div>
    </details>

    <details v-if="message.outlineGenerating" class="msg-collapse" open>
      <summary class="collapse-summary">Document Outline (generating...)</summary>
      <div class="collapse-body">
        <div v-html="renderMd(message.outlineGenerating)"></div>
        <span class="blink-cursor">|</span>
      </div>
    </details>

    <div v-if="message.outlineError" class="error-block">
      <strong>Outline Error:</strong> {{ message.outlineError }}
    </div>

    <template v-for="(part, i) in message.completedParts" :key="'p' + i">
      <details class="msg-collapse">
        <summary class="collapse-summary">Part {{ i + 1 }}: {{ part.heading }}</summary>
        <div class="collapse-body" v-html="renderMd(part.content)"></div>
      </details>
    </template>

    <div v-if="message.currentPartIdx != null" class="current-part">
      <h4>Part {{ (message.currentPartIdx ?? 0) + 1 }}: {{ message.currentPartHeading }} (generating...)</h4>
      <div v-if="message.currentPartContent" v-html="renderMd(message.currentPartContent)"></div>
      <span v-if="message.streaming" class="blink-cursor">|</span>
    </div>

    <template v-if="!message.streaming && message.docContent">
      <details class="msg-collapse" open>
        <summary class="collapse-summary">Full Document</summary>
        <div class="collapse-body" v-html="renderMd(message.docContent)"></div>
      </details>
      <div v-if="message.downloadUrlMd || message.downloadUrlDocx" class="download-links">
        <a v-if="message.downloadUrlMd" :href="message.downloadUrlMd + '?download=1'" class="download-btn md" target="_blank">
          Download (.md)
        </a>
        <a v-if="message.downloadUrlDocx" :href="message.downloadUrlDocx + '?download=1'" class="download-btn docx" target="_blank">
          Download (.docx)
        </a>
      </div>
    </template>
  </div>
</template>

<script setup>
import { renderMarkdown } from '@/utils/markdown.js'

defineProps({
  message: { type: Object, required: true },
})

function renderMd(text) {
  return renderMarkdown(text || '')
}
</script>