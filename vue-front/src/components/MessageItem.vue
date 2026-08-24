<template>
  <div class="message-item" :class="[phaseClass, { streaming: message.streaming }]">
    <div class="phase-badge" v-if="phaseLabel">{{ phaseLabel }}</div>
    <div class="message-content">
      <template v-if="message.type === 'user'">
        <details v-if="message.collapsed" class="msg-collapse">
          <summary class="collapse-summary">{{ userSummary }}</summary>
          <div class="collapse-body" v-html="renderedContent"></div>
        </details>
        <div v-else class="message-body" v-html="renderedContent"></div>
      </template>

      <template v-else-if="message.type === 'stream' && message.phase === 'think'">
        <details class="msg-collapse">
          <summary class="collapse-summary">Plan</summary>
          <div class="collapse-body">
            <div v-if="message.planResult" class="plan-display" v-html="formattedPlan"></div>
            <div v-else class="streaming-content" v-html="renderedContent"></div>
            <span v-if="message.streaming" class="blink-cursor">|</span>
          </div>
        </details>
      </template>

      <template v-else-if="message.type === 'stream' && message.phase === 'action_decision'">
        <details class="msg-collapse" :open="false">
          <summary class="collapse-summary">Decision</summary>
          <div class="collapse-body" v-html="renderedContent"></div>
        </details>
      </template>

      <template v-else-if="message.type === 'stream' && message.phase === 'observe'">
        <details class="msg-collapse" :open="false">
          <summary class="collapse-summary">Updated Plan</summary>
          <div class="collapse-body">
            <div v-if="message.planResult" class="plan-display" v-html="formattedPlan"></div>
            <div v-else v-html="renderedContent"></div>
          </div>
        </details>
      </template>

      <template v-else-if="message.type === 'stream' && message.phase === 'act'">
        <ActMessage :message="message" :server-url="serverUrl" />
      </template>

      <template v-else-if="message.type === 'stream' && message.phase === 'document'">
        <DocumentMessage :message="message" />
      </template>

      <template v-else-if="message.type === 'assistant'">
        <template v-if="message.phase === 'act'">
          <ActMessage :message="message" :server-url="serverUrl" />
        </template>
        <template v-else>
          <details v-if="message.collapsed" class="msg-collapse" :open="!message.collapsed">
            <summary class="collapse-summary">{{ assistantSummary }}</summary>
            <div class="collapse-body">
              <div v-if="message.phase === 'think' || message.phase === 'observe'">
                <div v-if="message.planResult" class="plan-display" v-html="formattedPlan"></div>
                <div v-else v-html="renderedContent"></div>
              </div>
              <div v-else-if="message.phase === 'action_decision'" v-html="renderedContent"></div>
              <div v-else v-html="renderedContent"></div>
            </div>
          </details>
          <div v-else class="message-body" v-html="renderedContent"></div>
        </template>
      </template>

      <template v-else-if="message.type === 'stream'">
        <div class="streaming-content" v-html="renderedContent"></div>
        <span v-if="message.streaming" class="blink-cursor">|</span>
      </template>

      <template v-else-if="message.type === 'error'">
        <div class="error-message" v-html="renderedContent"></div>
      </template>

      <template v-else-if="message.type === 'system'">
        <div class="system-message" v-html="renderedContent"></div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { renderMarkdown, renderMarkdownInline } from '@/utils/markdown.js'
import ActMessage from '@/components/ActMessage.vue'
import DocumentMessage from '@/components/DocumentMessage.vue'

const props = defineProps({
  message: { type: Object, required: true },
  serverUrl: { type: String, default: '' },
})

const renderedContent = computed(() => {
  return renderMarkdown(props.message.content || '')
})

const phaseLabel = computed(() => {
  return props.message.label || getPhaseLabel(props.message)
})

const phaseClass = computed(() => {
  const p = props.message.phase || ''
  if (p === 'think') return 'phase-think'
  if (p === 'action_decision' || p === 'act') return 'phase-act'
  if (p === 'observe') return 'phase-observe'
  if (props.message.type === 'user') return 'phase-user'
  if (props.message.type === 'error') return 'phase-error'
  return ''
})

const userSummary = computed(() => {
  const t = props.message.type || ''
  if (t === 'choice') return 'User Choice'
  if (t === 'response' || t === 'input') return 'User Input'
  return 'User'
})

const assistantSummary = computed(() => {
  const p = props.message.phase || ''
  if (p === 'think') return 'Plan'
  if (p === 'action_decision') return 'Decision'
  if (p === 'observe') return 'Updated Plan'
  const a = props.message.action || ''
  if (a === 'output_text') return 'Output'
  if (a === 'ask_question') return 'Question'
  if (a === 'ask_choice') return 'Choice'
  if (a === 'summary_and_pause') return 'Summary'
  if (a === 'attempt_completion') return 'Completion'
  if (a === 'explore_schema') return 'Explore Schema'
  if (a === 'explore_functions') return 'Explore Functions'
  if (a === 'generate_and_execute') return 'Generate & Execute'
  if (a === 'solved') return 'Solved'
  return a || 'Entry'
})

const formattedPlan = computed(() => {
  const plan = props.message.planResult
  if (!plan) return ''
  let html = renderMarkdown(plan.description || '')
  if (plan.todo?.length) {
    html += '<p><strong>Pending Tasks:</strong></p><ul>'
    for (const t of plan.todo) {
      html += `<li><input type="checkbox" disabled /> ${renderMarkdownInline(t)}</li>`
    }
    html += '</ul>'
  }
  return html
})

function getPhaseLabel(msg) {
  const p = msg.phase || ''
  if (p === 'think') return 'THINK - Planning'
  if (p === 'action_decision') return 'ACTION - Decide'
  if (p === 'observe') return 'OBSERVE - Review'
  if (p === 'act') return msg.label || `ACT - ${msg.action || ''}`
  return ''
}
</script>