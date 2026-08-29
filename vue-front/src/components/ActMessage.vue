<template>
  <div class="act-message">
    <template v-if="message.action === 'explore_schema'">
      <details v-if="message.explore_plan || message.parsed?.explore_plan" class="msg-collapse">
        <summary class="collapse-summary">Query Plan</summary>
        <div class="collapse-body" v-html="renderMd(message.explore_plan || message.parsed?.explore_plan)"></div>
      </details>
      <details v-if="hasSelectedFields" class="msg-collapse">
        <summary class="collapse-summary">Selected Fields</summary>
        <div class="collapse-body">
          <pre><code>{{ formatJson(selectedFields) }}</code></pre>
        </div>
      </details>
      <details v-if="hasSchemaDetail" class="msg-collapse">
        <summary class="collapse-summary">Search Results: explore_schema</summary>
        <div class="collapse-body" v-html="renderMd(schemaDetail)"></div>
      </details>
      <details v-if="hasSelectedGuides" class="msg-collapse">
        <summary class="collapse-summary">Selected Guides</summary>
        <div class="collapse-body">
          <pre><code>{{ formatJson(selectedGuides) }}</code></pre>
        </div>
      </details>
      <details v-if="hasQueryGuideContent" class="msg-collapse">
        <summary class="collapse-summary">Query Guide</summary>
        <div class="collapse-body" v-html="renderMd(queryGuideContent)"></div>
      </details>
    </template>

    <template v-else-if="message.action === 'explore_functions'">
      <details v-if="hasSelectedFunctions" class="msg-collapse">
        <summary class="collapse-summary">Selected Functions</summary>
        <div class="collapse-body">
          <pre><code>{{ formatJson(selectedFunctions) }}</code></pre>
        </div>
      </details>
      <details v-if="hasFuncDocs" class="msg-collapse">
        <summary class="collapse-summary">Search Results: explore_functions</summary>
        <div class="collapse-body" v-html="renderMd(funcDocs)"></div>
      </details>
    </template>

    <template v-else-if="message.action === 'generate_and_execute'">
      <template v-if="attempts.length">
        <div v-for="(att, i) in attempts" :key="i" class="attempt-block">
          <details class="msg-collapse" :open="i === attempts.length - 1">
            <summary class="collapse-summary">
              Attempt {{ i + 1 }}
              <span v-if="att.error" class="attempt-status error">❌</span>
              <span v-else-if="att.result" class="attempt-status success">✅</span>
            </summary>
            <div class="collapse-body">
              <details v-if="att.code" class="msg-collapse">
                <summary class="collapse-summary">Code (Attempt {{ i + 1 }})</summary>
                <div class="collapse-body">
                  <pre><code class="language-python">{{ att.code }}</code></pre>
                </div>
              </details>
              <details v-if="att.result" class="msg-collapse">
                <summary class="collapse-summary">Result (Attempt {{ i + 1 }})</summary>
                <div class="collapse-body" v-html="renderMd(att.result)"></div>
              </details>
              <div v-if="att.error" class="error-block">
                <strong>Error:</strong> {{ att.error }}
              </div>
            </div>
          </details>
        </div>
      </template>
      <template v-else>
        <details v-if="message.code" class="msg-collapse">
          <summary class="collapse-summary">Code</summary>
          <div class="collapse-body">
            <pre><code class="language-python">{{ message.code }}</code></pre>
          </div>
        </details>
        <details v-if="message.result" class="msg-collapse">
          <summary class="collapse-summary">Result</summary>
          <div class="collapse-body" v-html="renderMd(message.result)"></div>
        </details>
        <details v-if="message.error" class="msg-collapse">
          <summary class="collapse-summary">Error</summary>
          <div class="error-block">
            <strong>Error:</strong> {{ message.error }}
          </div>
        </details>
      </template>
    </template>

    <template v-else-if="message.action === 'web_search'">
      <details class="msg-collapse" open>
        <summary class="collapse-summary">Web Search Results</summary>
        <div class="collapse-body">
          <div v-if="message.query" class="search-query"><strong>Query:</strong> {{ message.query }}</div>
          <div v-if="hasSearchResult" v-html="renderMd(searchResult)"></div>
        </div>
      </details>
    </template>

    <template v-else-if="message.action === 'fetch_webpage'">
      <details class="msg-collapse" open>
        <summary class="collapse-summary">Fetched Webpage</summary>
        <div class="collapse-body">
          <div v-if="message.url" class="search-query"><strong>URL:</strong> {{ message.url }}</div>
          <div v-if="hasPageContent" v-html="renderMd(pageContent)"></div>
        </div>
      </details>
    </template>

    <template v-else-if="message.action === 'generate_document'">
      <details class="msg-collapse" open>
        <summary class="collapse-summary">Document generated</summary>
        <div class="collapse-body">
          <div v-if="message.title" class="doc-title">{{ message.title }}</div>
          <div v-if="message.file_name" class="file-actions">
            <a :href="`${serverUrl}/tmp_imgs/${message.file_name}.md?download=1`" target="_blank" class="download-btn md">.md</a>
            <a :href="`${serverUrl}/tmp_imgs/${message.file_name}.docx?download=1`" target="_blank" class="download-btn docx">.docx</a>
            <a :href="`${serverUrl}/tmp_imgs/${message.file_name}.pdf?download=1`" target="_blank" class="download-btn pdf">.pdf</a>
          </div>
          <div v-if="message.full_text" class="doc-full-text" v-html="renderMd(message.full_text)"></div>
        </div>
      </details>
    </template>

    <template v-else-if="message.action === 'solved'">
      <div class="solved-content" v-html="renderMd(message.solved_ans || '')"></div>
    </template>

    <template v-else-if="isFrontendAction">
      <details class="msg-collapse" :open="!message.collapsed">
        <summary class="collapse-summary">{{ frontendActionLabel }}</summary>
        <div class="collapse-body" v-html="renderMd(message.text || '')"></div>
      </details>
    </template>

    <template v-else>
      <details v-if="hasSearchResult" class="msg-collapse">
        <summary class="collapse-summary">Search Results: {{ message.action }}</summary>
        <div class="collapse-body" v-html="renderMd(searchResult)"></div>
      </details>
      <div v-else class="raw-content">
        <pre><code>{{ formatJson(message) }}</code></pre>
      </div>
    </template>

    <template v-if="message.subPhases?.length">
      <div v-for="sub in message.subPhases" :key="sub.name" class="sub-phase">
        <details class="msg-collapse" :open="sub.name === 'generate_document' || sub.name === 'completion'">
          <summary class="collapse-summary">{{ subPhaseLabel(sub.name) }}</summary>
          <div class="collapse-body">
            <div v-if="sub.name === 'explore_schema' || sub.name === 'explore_functions'">
              <div v-html="renderMd(sub.content)"></div>
            </div>
            <div v-else v-html="renderMd(sub.content)"></div>
            <span v-if="sub.streaming" class="blink-cursor">|</span>
          </div>
        </details>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { renderMarkdown } from '@/utils/markdown.js'

const props = defineProps({
  message: { type: Object, required: true },
  serverUrl: { type: String, default: import.meta.env.VITE_SERVER_URL || 'http://127.0.0.1:8009' },
})

const FRONTEND_ACTIONS = ['output_text', 'ask_question', 'ask_choice', 'summary_and_pause', 'attempt_completion']

const isFrontendAction = computed(() => FRONTEND_ACTIONS.includes(props.message.action))

const frontendActionLabel = computed(() => {
  const a = props.message.action
  if (a === 'output_text') return 'Output'
  if (a === 'ask_question') return 'Question'
  if (a === 'ask_choice') return 'Choice'
  if (a === 'summary_and_pause') return 'Summary'
  if (a === 'attempt_completion') return 'Completion'
  return a
})

const attempts = computed(() => {
  return props.message.attempts || props.message.parsed?.attempts || []
})

const selectedFields = computed(() => {
  return props.message.selected_fields || props.message.parsed?.selected_fields
})

const hasSelectedFields = computed(() => selectedFields.value != null)

const selectedFunctions = computed(() => {
  return props.message.selected_functions || props.message.parsed?.selected_functions
})

const hasSelectedFunctions = computed(() => selectedFunctions.value != null)

const funcDocs = computed(() => {
  return props.message.func_docs || props.message.parsed?.func_docs
})

const hasFuncDocs = computed(() => !!funcDocs.value)

const schemaDetail = computed(() => {
  return props.message.schema_detail || props.message.parsed?.schema_detail
})

const hasSchemaDetail = computed(() => !!schemaDetail.value)

const selectedGuides = computed(() => {
  return props.message.selected_guides || props.message.parsed?.selected_guides || []
})

const hasSelectedGuides = computed(() => selectedGuides.value.length > 0)

const queryGuideContent = computed(() => {
  return props.message.query_guide_content || props.message.parsed?.query_guide_content || ''
})

const hasQueryGuideContent = computed(() => !!queryGuideContent.value)

const searchResult = computed(() => {
  const sub = props.message.subPhases?.find(s => s.name === 'web_search')
  return props.message.search_result || props.message.parsed?.search_result || sub?.content || ''
})

const hasSearchResult = computed(() => !!searchResult.value)

const pageContent = computed(() => {
  const sub = props.message.subPhases?.find(s => s.name === 'fetch_webpage')
  return props.message.page_content || props.message.parsed?.page_content || sub?.content || ''
})

const hasPageContent = computed(() => !!pageContent.value)

function renderMd(text) {
  return renderMarkdown(text || '')
}

function formatJson(obj) {
  try {
    return JSON.stringify(obj, null, 2)
  } catch {
    return String(obj)
  }
}

function subPhaseLabel(name) {
  const labels = {
    explore_schema: 'Search Results: explore_schema',
    explore_functions: 'Search Results: explore_functions',
    generate: 'Generated Code',
    code: 'Generated Code',
    exec: 'Execution Output',
    output_text: 'Output',
    summary: 'Summary',
    completion: 'Completion',
    ask_question: 'Question',
    ask_choice: 'Choice',
    generate_document: 'Generated Document',
    web_search: 'Web Search Results',
    fetch_webpage: 'Fetched Webpage',
  }
  return labels[name] || name
}
</script>