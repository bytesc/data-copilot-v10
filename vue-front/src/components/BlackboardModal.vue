<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal-content blackboard-modal">
      <h3 class="blackboard-header">
        <span>Blackboard</span>
        <span class="blackboard-count">{{ filledRegions }}/4</span>
        <button class="bb-close" type="button" @click="$emit('close')">✕</button>
      </h3>

      <div class="modal-body blackboard-body">
        <details class="bb-region">
          <summary class="bb-region-title">DB</summary>
          <div class="bb-region-body">
            <div v-if="has(schema)" class="bb-block">
              <template v-if="schema.selected_fields != null">
                <div class="bb-label">Selected Fields</div>
                <pre class="bb-json">{{ formatJson(schema.selected_fields) }}</pre>
              </template>
              <template v-if="schema.explore_plan">
                <div class="bb-label">Plan</div>
                <div class="bb-md" v-html="renderMarkdown(schema.explore_plan)"></div>
              </template>
              <template v-if="hasList(schema.selected_guides)">
                <div class="bb-label">Selected Guides</div>
                <pre class="bb-json">{{ formatJson(schema.selected_guides) }}</pre>
              </template>
              <template v-if="schema.query_guide_content">
                <div class="bb-label">Query Guide</div>
                <div class="bb-md" v-html="renderMarkdown(schema.query_guide_content)"></div>
              </template>
              <template v-if="schema.schema_detail">
                <div class="bb-label">Schema</div>
                <div class="bb-md" v-html="renderMarkdown(schema.schema_detail)"></div>
              </template>
            </div>
            <div v-else class="bb-empty">No DB content</div>
          </div>
        </details>

        <details class="bb-region">
          <summary class="bb-region-title">FUNC</summary>
          <div class="bb-region-body">
            <div v-if="has(functions)" class="bb-block">
              <template v-if="hasList(functions.selected_functions)">
                <div class="bb-label">Selected Functions</div>
                <pre class="bb-json">{{ formatJson(functions.selected_functions) }}</pre>
              </template>
              <template v-if="functions.explore_plan">
                <div class="bb-label">Plan</div>
                <div class="bb-md" v-html="renderMarkdown(functions.explore_plan)"></div>
              </template>
              <template v-if="functions.func_docs">
                <div class="bb-label">Function Docs</div>
                <div class="bb-md" v-html="renderMarkdown(functions.func_docs)"></div>
              </template>
            </div>
            <div v-else class="bb-empty">No function content</div>
          </div>
        </details>

        <details class="bb-region">
          <summary class="bb-region-title">KNOWLEDGE</summary>
          <div class="bb-region-body">
            <div v-if="has(knowledge)" class="bb-block">
              <template v-if="hasList(knowledge.selected_knowledge_ids)">
                <div class="bb-label">Selected IDs</div>
                <pre class="bb-json">{{ formatJson(knowledge.selected_knowledge_ids) }}</pre>
              </template>
              <template v-if="knowledge.summary">
                <div class="bb-label">Summary</div>
                <div class="bb-md" v-html="renderMarkdown(knowledge.summary)"></div>
              </template>
              <template v-if="knowledge.knowledge_content">
                <div class="bb-label">Knowledge</div>
                <div class="bb-md" v-html="renderMarkdown(knowledge.knowledge_content)"></div>
              </template>
            </div>
            <div v-else class="bb-empty">No knowledge content</div>
          </div>
        </details>

        <details class="bb-region">
          <summary class="bb-region-title">MCP</summary>
          <div class="bb-region-body">
            <div v-if="has(mcp)" class="bb-block">
              <template v-if="hasList(mcp.selected_tools)">
                <div class="bb-label">Selected Tools</div>
                <pre class="bb-json">{{ formatJson(mcp.selected_tools) }}</pre>
              </template>
              <template v-if="mcp.explore_plan">
                <div class="bb-label">Plan</div>
                <div class="bb-md" v-html="renderMarkdown(mcp.explore_plan)"></div>
              </template>
              <template v-if="mcp.tool_detail">
                <div class="bb-label">Tool Detail</div>
                <div class="bb-md" v-html="renderMarkdown(mcp.tool_detail)"></div>
              </template>
              <template v-if="mcp.catalog">
                <div class="bb-label">Catalog</div>
                <div class="bb-md" v-html="renderMarkdown(mcp.catalog)"></div>
              </template>
            </div>
            <div v-else class="bb-empty">No MCP content</div>
          </div>
        </details>
      </div>

      <div class="modal-actions">
        <button class="btn-secondary" @click="$emit('close')">Close</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { renderMarkdown } from '@/utils/markdown.js'

const props = defineProps({
  board: { type: Object, default: () => ({}) },
})

defineEmits(['close'])

const schema = computed(() => props.board?.schema || {})
const functions = computed(() => props.board?.functions || {})
const knowledge = computed(() => props.board?.knowledge || {})
const mcp = computed(() => props.board?.mcp || {})

const filledRegions = computed(() => [schema, functions, knowledge, mcp].filter(r => has(r.value)).length)

function has(region) {
  return !!region && Object.keys(region).some(k => {
    const v = region[k]
    return v !== null && v !== undefined && v !== '' && !(Array.isArray(v) && v.length === 0)
  })
}

function hasList(value) {
  return Array.isArray(value) && value.length > 0
}

function formatJson(value) {
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}
</script>

<style scoped>
.blackboard-modal {
  width: 1100px;
  max-width: 96vw;
  height: 88vh;
  max-height: 92vh;
}

.blackboard-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.blackboard-count {
  font-size: 11px;
  font-weight: 400;
  color: var(--text-muted);
}

.bb-close {
  margin-left: auto;
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 16px;
  cursor: pointer;
  line-height: 1;
  padding: 2px 4px;
}

.bb-close:hover {
  color: var(--text-primary);
}

.blackboard-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.bb-region {
  border: 1px solid var(--border-color);
  border-radius: calc(var(--radius) - 2px);
  background: var(--bg-tertiary);
}

.bb-region-title {
  cursor: pointer;
  padding: 8px 12px;
  font-size: 12px;
  font-weight: 600;
  color: var(--accent-blue);
  letter-spacing: 0.5px;
  user-select: none;
}

.bb-region-title::-webkit-details-marker {
  display: none;
}

.bb-region-title::before {
  content: '▸';
  margin-right: 6px;
  color: var(--text-muted);
}

.bb-region[open] > .bb-region-title::before {
  content: '▾';
}

.bb-region-body {
  border-top: 1px solid var(--border-color);
  padding: 10px 12px 12px;
  max-height: 45vh;
  overflow: auto;
}

.bb-label {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  color: var(--text-muted);
  margin: 10px 0 4px;
}

.bb-region-body .bb-label:first-child {
  margin-top: 0;
}

.bb-json {
  margin: 0;
  padding: 6px 8px;
  font-size: 11px;
  line-height: 1.4;
  background: var(--bg-primary, rgba(0, 0, 0, 0.15));
  border-radius: 4px;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

.bb-md {
  font-size: 12px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.bb-md :deep(table) {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
}

.bb-md :deep(th),
.bb-md :deep(td) {
  border: 1px solid var(--border-color);
  padding: 3px 6px;
  text-align: left;
}

.bb-empty {
  font-size: 12px;
  color: var(--text-muted);
}

@media (max-width: 768px) {
  .blackboard-modal {
    width: 96vw;
    max-width: 96vw;
    height: 92vh;
    max-height: 92vh;
  }

  .blackboard-header {
    padding: 12px 14px;
    font-size: 15px;
  }

  .blackboard-body {
    padding: 12px;
    gap: 6px;
  }

  .bb-region-title {
    padding: 10px 12px;
    font-size: 12px;
  }

  .bb-region-body {
    max-height: 38vh;
    padding: 8px 10px 10px;
  }

  .bb-md {
    font-size: 13px;
  }

  .bb-json {
    font-size: 12px;
  }

  .modal-actions {
    padding: 10px 14px;
    padding-bottom: calc(10px + env(safe-area-inset-bottom, 0px));
  }
}
</style>
