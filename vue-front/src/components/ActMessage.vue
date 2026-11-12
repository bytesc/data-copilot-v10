<template>
  <div class="act-message">
    <ThinkingBlock :message="message" />
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
    </template>

    <template v-else-if="message.action === 'explore_base_knowledge'">
      <details v-if="hasSelectedKnowledgeIds" class="msg-collapse">
        <summary class="collapse-summary">Selected Knowledge IDs</summary>
        <div class="collapse-body">
          <pre><code>{{ formatJson(selectedKnowledgeIds) }}</code></pre>
        </div>
      </details>
      <details v-if="hasSummary" class="msg-collapse">
        <summary class="collapse-summary">Summary</summary>
        <div class="collapse-body" v-html="renderMd(summary)"></div>
      </details>
    </template>

    <template v-else-if="message.action === 'explore_functions'">
      <details v-if="message.explore_plan || message.parsed?.explore_plan" class="msg-collapse">
        <summary class="collapse-summary">Call Plan</summary>
        <div class="collapse-body" v-html="renderMd(message.explore_plan || message.parsed?.explore_plan)"></div>
      </details>
      <details v-if="hasSelectedFunctions" class="msg-collapse">
        <summary class="collapse-summary">Selected Functions</summary>
        <div class="collapse-body">
          <pre><code>{{ formatJson(selectedFunctions) }}</code></pre>
        </div>
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
              <details v-if="att.result" class="msg-collapse" open>
                <summary class="collapse-summary">Result (Attempt {{ i + 1 }})</summary>
                <div class="collapse-body" v-html="renderMd(att.result)"></div>
              </details>
              <details v-if="att.images?.length" class="msg-collapse">
                <summary class="collapse-summary">Images ({{ att.images.length }})</summary>
                <div class="collapse-body">
                  <div class="images-grid">
                    <a v-for="(src, j) in att.images" :key="j" :href="imageSrc(src)" target="_blank" class="image-item">
                      <img :src="imageSrc(src)" alt="generated image" loading="lazy" />
                      <span class="image-name">{{ imageName(src) }}</span>
                    </a>
                  </div>
                </div>
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
        <details v-if="message.result" class="msg-collapse" open>
          <summary class="collapse-summary">Result</summary>
          <div class="collapse-body" v-html="renderMd(message.result)"></div>
        </details>
        <details v-if="hasImages" class="msg-collapse">
          <summary class="collapse-summary">Images ({{ images.length }})</summary>
          <div class="collapse-body">
            <div class="images-grid">
              <a v-for="(src, j) in images" :key="j" :href="imageSrc(src)" target="_blank" class="image-item">
                <img :src="imageSrc(src)" alt="generated image" loading="lazy" />
                <span class="image-name">{{ imageName(src) }}</span>
              </a>
            </div>
          </div>
        </details>
        <details v-if="message.error" class="msg-collapse">
          <summary class="collapse-summary">
            Error<template v-if="message.error_kind"> · {{ message.error_kind }}</template>
          </summary>
          <div class="error-block">
            <strong>Error:</strong> {{ message.error }}
          </div>
        </details>
      </template>
    </template>

    <template v-else-if="message.action === 'select_images'">
      <details class="msg-collapse" open>
        <summary class="collapse-summary">Selected Images ({{ selectedImages.length }})</summary>
        <div class="collapse-body">
          <div v-if="hasSelectedImages" class="images-grid">
            <div v-for="(item, i) in selectedImages" :key="i" class="image-item">
              <a :href="imageSrc(item.path)" target="_blank">
                <img :src="imageSrc(item.path)" :alt="item.reason || 'selected image'" loading="lazy" />
              </a>
              <span class="image-name">{{ imageName(item.path) }}</span>
              <span class="image-reason">{{ item.reason || '(no reason)' }}</span>
            </div>
          </div>
          <div v-else class="raw-content">No images selected.</div>
        </div>
      </details>
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

    <template v-else-if="message.action === 'explore_mcp'">
      <details v-if="hasMcpExplorePlan" class="msg-collapse">
        <summary class="collapse-summary">MCP Tool Selection Plan</summary>
        <div class="collapse-body" v-html="renderMd(mcpExplorePlan)"></div>
      </details>
      <details v-if="hasMcpSelectedTools" class="msg-collapse">
        <summary class="collapse-summary">Selected MCP Tools</summary>
        <div class="collapse-body">
          <pre><code>{{ formatJson(mcpSelectedTools) }}</code></pre>
        </div>
      </details>
    </template>

    <template v-else-if="message.action === 'exe_mcp'">
      <details class="msg-collapse" open>
        <summary class="collapse-summary">MCP Execute{{ mcpSummaryLabel }}</summary>
        <div class="collapse-body">
          <div v-if="message.error" class="error-block"><strong>Error:</strong> {{ message.error }}</div>
          <div v-if="hasMcpResults">
            <div v-for="(r, i) in mcpResults" :key="i" class="mcp-tool-entry">
              <div class="mcp-tool-header">{{ r.server }}/{{ r.tool }}</div>
              <div v-if="r.error" class="error-block"><strong>Error:</strong> {{ r.error }}</div>
              <div v-else class="mcp-result"><pre><code>{{ formatJson(r.result) }}</code></pre></div>
            </div>
          </div>
          <div v-else-if="hasMcpResult" class="mcp-result"><pre><code>{{ formatJson(message.result) }}</code></pre></div>
        </div>
      </details>
    </template>

    <template v-else-if="message.action === 'generate_document'">
      <details class="msg-collapse" open>
        <summary class="collapse-summary">Document generated</summary>
        <div class="collapse-body">
          <div v-if="message.title" class="doc-title">{{ message.title }}</div>
          <div v-if="message.downloadUrlMd || message.downloadUrlDocx || message.downloadUrlPdf" class="file-actions">
            <a :href="message.downloadUrlMd + '?download=1'" target="_blank" class="download-btn md">.md</a>
            <a :href="message.downloadUrlDocx + '?download=1'" target="_blank" class="download-btn docx">.docx</a>
            <a :href="message.downloadUrlPdf + '?download=1'" target="_blank" class="download-btn pdf">.pdf</a>
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
      <div v-for="sub in message.subPhases" v-show="!isExploreSubPhase(sub.name)" :key="sub.name" class="sub-phase">
        <details class="msg-collapse" :open="sub.name === 'generate_document' || sub.name === 'completion'">
          <summary class="collapse-summary">{{ subPhaseLabel(sub.name) }}</summary>
          <div class="collapse-body">
            <div v-if="sub.name === 'explore_schema' || sub.name === 'explore_functions' || sub.name === 'explore_base_knowledge' || sub.name === 'explore_mcp'">
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
import ThinkingBlock from '@/components/ThinkingBlock.vue'

const props = defineProps({
  message: { type: Object, required: true },
})

const FRONTEND_ACTIONS = ['ask_question', 'ask_choice', 'summary_and_pause', 'attempt_completion']

const isFrontendAction = computed(() => FRONTEND_ACTIONS.includes(props.message.action))

const frontendActionLabel = computed(() => {
  const a = props.message.action
  if (a === 'ask_question') return 'Question'
  if (a === 'ask_choice') return 'Choice'
  if (a === 'summary_and_pause') return 'Summary'
  if (a === 'attempt_completion') return 'Completion'
  return a
})

const attempts = computed(() => {
  return props.message.attempts || props.message.parsed?.attempts || []
})

const images = computed(() => {
  return props.message.images || props.message.parsed?.images || []
})

const hasImages = computed(() => images.value.length > 0)

const selectedImages = computed(() => {
  const list = props.message.selected_images || props.message.parsed?.selected_images || []
  return Array.isArray(list) ? list.filter(item => item && item.path) : []
})

const hasSelectedImages = computed(() => selectedImages.value.length > 0)

const IMAGE_BASE_URL = window.location.origin

function imageSrc(src) {
  if (!src) return ''
  if (/^https?:\/\//i.test(src) || /^data:image\//i.test(src)) return src
  const clean = String(src).replace(/^\/?tmp_imgs\//i, '')
  return `${IMAGE_BASE_URL}/tmp_imgs/${clean}`
}

function imageName(src) {
  if (!src) return ''
  const parts = String(src).split('/')
  return parts[parts.length - 1] || src
}

const selectedFields = computed(() => {
  return props.message.selected_fields || props.message.parsed?.selected_fields
})

const hasSelectedFields = computed(() => selectedFields.value != null)

const selectedKnowledgeIds = computed(() => {
  return props.message.selected_knowledge_ids || props.message.parsed?.selected_knowledge_ids
})

const hasSelectedKnowledgeIds = computed(() => selectedKnowledgeIds.value != null)

const summary = computed(() => {
  return props.message.summary || props.message.parsed?.summary
})

const hasSummary = computed(() => !!summary.value)

const selectedFunctions = computed(() => {
  return props.message.selected_functions || props.message.parsed?.selected_functions
})

const hasSelectedFunctions = computed(() => selectedFunctions.value != null)

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

const mcpExplorePlan = computed(() => {
  return props.message.explore_plan || props.message.parsed?.explore_plan || ''
})

const hasMcpExplorePlan = computed(() => !!mcpExplorePlan.value)

const mcpSelectedTools = computed(() => {
  return props.message.selected_tools || props.message.parsed?.selected_tools || []
})

const hasMcpSelectedTools = computed(() => mcpSelectedTools.value.length > 0)

const mcpResults = computed(() => {
  return props.message.results || props.message.parsed?.results || []
})

const hasMcpResults = computed(() => mcpResults.value.length > 0)

const mcpSummaryLabel = computed(() => {
  const results = mcpResults.value
  if (results.length === 1) {
    return `: ${results[0].server}/${results[0].tool}`
  }
  if (results.length > 1) {
    return ` (${results.length} tools)`
  }
  if (props.message.server || props.message.tool) {
    return `: ${props.message.server || ''}/${props.message.tool || ''}`
  }
  return ''
})

const mcpDisplayContent = computed(() => {
  return props.message.display_content || props.message.parsed?.display_content || ''
})

const hasMcpDisplayContent = computed(() => !!mcpDisplayContent.value)

function mcpResultText(r) {
  const result = r.result || r
  if (!result) return ''
  const content = result.content || result
  if (typeof content === 'string') return content
  return formatJson(content)
}

const mcpResultSingleText = computed(() => {
  const r = props.message.result || props.message.parsed?.result
  if (!r) return ''
  if (typeof r === 'string') return r
  return formatJson(r)
})

const hasMcpResult = computed(() => {
  return props.message.result || props.message.parsed?.result
})

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

const EXPLORE_SUB_PHASES = new Set(['explore_schema', 'explore_functions', 'explore_base_knowledge', 'explore_mcp'])

function isExploreSubPhase(name) {
  return EXPLORE_SUB_PHASES.has(name)
}

function subPhaseLabel(name) {
  const labels = {
    explore_schema: 'Search Results: explore_schema',
    explore_base_knowledge: 'Search Results: explore_base_knowledge',
    explore_functions: 'Search Results: explore_functions',
    generate: 'Generated Code',
    code: 'Generated Code',
    exec: 'Execution Output',
    summary: 'Summary',
    completion: 'Completion',
    ask_question: 'Question',
    ask_choice: 'Choice',
    generate_document: 'Generated Document',
    web_search: 'Web Search Results',
    fetch_webpage: 'Fetched Webpage',
    explore_mcp: 'MCP Tools',
    exe_mcp: 'MCP Execution Result',
    select_images: 'Selected Images',
  }
  return labels[name] || name
}
</script>

<style scoped>
.mcp-tool-entry {
  padding: 6px 0;
  border-bottom: 1px solid var(--border-color);
}
.mcp-tool-entry:last-child {
  border-bottom: none;
}
.mcp-tool-header {
  font-size: 14px;
  margin-bottom: 2px;
}
.mcp-tool-desc {
  font-size: 12px;
  color: var(--text-secondary);
}
.mcp-result {
  white-space: pre-wrap;
}
.error-block {
  color: var(--accent-red);
  padding: 8px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-sm);
  margin: 4px 0;
}
.search-query {
  margin-bottom: 8px;
  font-size: 13px;
}
.images-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.image-item {
  display: block;
  max-width: 240px;
  flex: 1 1 auto;
}
.image-item img {
  display: block;
  width: 100%;
  border-radius: calc(var(--radius) - 2px);
  border: 1px solid var(--border-color);
  background: var(--bg-primary, rgba(0, 0, 0, 0.15));
}
.image-name {
  display: block;
  margin-top: 4px;
  font-size: 11px;
  color: var(--text-muted);
  text-align: center;
  word-break: break-all;
}
.image-reason {
  display: block;
  margin-top: 3px;
  font-size: 11px;
  line-height: 1.35;
  color: var(--text-secondary, var(--text-muted));
  word-break: break-word;
}
</style>