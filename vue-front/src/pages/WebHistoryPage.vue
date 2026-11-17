<template>
  <div class="web-history-page">
    <div class="toolbar">
      <div class="filter-tabs">
        <button
          v-for="f in filters"
          :key="f.value"
          class="filter-tab"
          :class="{ active: filter === f.value }"
          @click="filter = f.value"
        >
          {{ f.label }}
        </button>
      </div>
      <div class="toolbar-right">
        <input
          v-model="search"
          type="text"
          class="form-input search-input"
          placeholder="Search by query, URL or session ID..."
        />
        <button class="btn-secondary btn-sm" :disabled="loading" @click="loadLogs">
          {{ loading ? 'Loading...' : 'Refresh' }}
        </button>
      </div>
    </div>

    <div class="page-body">
      <div v-if="loading && logs.length === 0" class="state-text">Loading...</div>
      <div v-else-if="error" class="state-text error-text">{{ error }}</div>
      <div v-else-if="filteredLogs.length === 0" class="state-text">No web access records found</div>
      <div v-else class="log-list">
        <div v-for="log in filteredLogs" :key="log.id" class="log-card">
          <div class="log-main">
            <div class="log-top">
              <span class="type-badge" :class="accessTypeClass(log.access_type)">
                {{ accessTypeLabel(log.access_type) }}
              </span>
              <span v-if="log.success" class="badge badge-success">Success</span>
              <span v-else class="badge badge-fail">Failed</span>
              <span v-if="log.session_id" class="session-ref">{{ log.session_id }}</span>
            </div>
            <div class="log-target">{{ targetText(log) }}</div>
            <div v-if="log.error" class="log-error">Error: {{ log.error }}</div>
            <div class="log-meta">
              <span v-if="log.created_at">Time: {{ formatTime(log.created_at) }}</span>
              <span v-if="log.duration_ms != null">Duration: {{ log.duration_ms }} ms</span>
            </div>
          </div>
          <div class="log-actions">
            <button class="btn-action" @click="viewLog(log)">View</button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="detailLog" class="modal-overlay" @click.self="closeDetail">
      <div class="modal-content">
        <div class="modal-header">
          <h3>{{ accessTypeLabel(detailLog.access_type) }} · #{{ detailLog.id }}</h3>
          <button class="modal-close" @click="closeDetail">×</button>
        </div>
        <div class="modal-body">
          <div v-if="detailLoading" class="state-text">Loading record...</div>
          <div v-else-if="detailError" class="state-text error-text">{{ detailError }}</div>
          <template v-else>
            <div class="detail-grid">
              <div class="detail-item"><span class="detail-key">Time</span><span class="detail-val">{{ formatTime(detailLog.created_at) }}</span></div>
              <div class="detail-item"><span class="detail-key">Success</span><span class="detail-val">{{ detailLog.success ? 'Yes' : 'No' }}</span></div>
              <div class="detail-item"><span class="detail-key">Duration</span><span class="detail-val">{{ detailLog.duration_ms != null ? detailLog.duration_ms + ' ms' : '-' }}</span></div>
              <div class="detail-item"><span class="detail-key">Session</span><span class="detail-val">{{ detailLog.session_id || '-' }}</span></div>
            </div>
            <div v-if="detailErrorText" class="detail-block">
              <div class="detail-block-label">Error</div>
              <pre class="detail-pre">{{ detailErrorText }}</pre>
            </div>
            <div v-if="detailQuery" class="detail-block">
              <div class="detail-block-label">Query</div>
              <pre class="detail-pre">{{ detailQuery }}</pre>
            </div>
            <div v-if="detailUrls.length" class="detail-block">
              <div class="detail-block-label">URLs</div>
              <div class="url-list">
                <a v-for="(u, i) in detailUrls" :key="i" :href="u" target="_blank" rel="noopener" class="url-link">{{ u }}</a>
              </div>
            </div>
            <div class="detail-block">
              <div class="detail-block-label">Result</div>
              <pre class="detail-pre">{{ formatJson(rawResult) }}</pre>
            </div>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { fetchWebAccessLogs, fetchWebAccessLogDetail } from '@/utils/api.js'

const filters = [
  { value: 'all', label: 'All' },
  { value: 'web_search', label: 'Web Search' },
  { value: 'fetch_webpage', label: 'Fetch URL' },
]

const logs = ref([])
const loading = ref(false)
const error = ref('')
const filter = ref('all')
const search = ref('')

const detailLog = ref(null)
const detailRaw = ref(null)
const detailLoading = ref(false)
const detailError = ref('')

function accessTypeLabel(type) {
  if (type === 'web_search') return 'Web Search'
  if (type === 'fetch_webpage') return 'Fetch URL'
  return type || 'Unknown'
}

function accessTypeClass(type) {
  if (type === 'web_search') return 'type-search'
  if (type === 'fetch_webpage') return 'type-fetch'
  return 'type-other'
}

function parseUrls(value) {
  if (!value) return []
  if (Array.isArray(value)) return value
  try {
    const parsed = JSON.parse(value)
    return Array.isArray(parsed) ? parsed : [String(value)]
  } catch (_) {
    return [String(value)]
  }
}

function targetText(log) {
  if (log.access_type === 'web_search') {
    return log.query ? `Query: ${log.query}` : '(no query)'
  }
  const urls = parseUrls(log.urls)
  return urls.length ? urls.join(', ') : '(no url)'
}

const filteredLogs = computed(() => {
  const term = search.value.trim().toLowerCase()
  return logs.value.filter((log) => {
    if (filter.value !== 'all' && log.access_type !== filter.value) return false
    if (term) {
      const haystack = [
        log.query || '',
        log.urls || '',
        log.session_id || '',
        log.error || '',
      ].join(' ').toLowerCase()
      if (!haystack.includes(term)) return false
    }
    return true
  })
})

const rawResult = computed(() => detailRaw.value?.result ?? detailLog.value?.result ?? '')
const detailQuery = computed(() => detailLog.value?.query || '')
const detailUrls = computed(() => parseUrls(detailLog.value?.urls))
const detailErrorText = computed(() => detailLog.value?.error || '')

function formatTime(value) {
  if (!value) return ''
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return String(value)
  return d.toLocaleString()
}

function formatJson(value) {
  if (value === undefined || value === null || value === '') return '(empty)'
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value, null, 2)
    } catch (_) {
      return String(value)
    }
  }
  const text = String(value)
  try {
    return JSON.stringify(JSON.parse(text), null, 2)
  } catch (_) {
    return text
  }
}

async function loadLogs() {
  loading.value = true
  error.value = ''
  try {
    logs.value = await fetchWebAccessLogs(200)
  } catch (e) {
    error.value = `Load failed: ${e.message}`
  } finally {
    loading.value = false
  }
}

async function viewLog(log) {
  detailLog.value = log
  detailRaw.value = null
  detailError.value = ''
  detailLoading.value = true
  try {
    detailRaw.value = await fetchWebAccessLogDetail(log.id)
  } catch (e) {
    detailError.value = `Load failed: ${e.message}`
  } finally {
    detailLoading.value = false
  }
}

function closeDetail() {
  detailLog.value = null
  detailRaw.value = null
  detailError.value = ''
}

onMounted(loadLogs)
</script>

<style scoped>
.web-history-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 24px;
  border-bottom: 1px solid var(--border-color);
  background: var(--bg-secondary);
  flex-shrink: 0;
  flex-wrap: wrap;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  justify-content: flex-end;
}

.filter-tabs {
  display: flex;
  gap: 4px;
}

.filter-tab {
  padding: 5px 14px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.filter-tab:hover {
  color: var(--text-primary);
}

.filter-tab.active {
  color: var(--accent-blue);
  border-color: var(--accent-blue);
}

.search-input {
  flex: 1;
  min-width: 180px;
  max-width: 360px;
}

.page-body {
  flex: 1;
  padding: 16px 24px;
  overflow-y: auto;
}

.log-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.log-card {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
}

.log-main {
  min-width: 0;
  flex: 1;
}

.log-top {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.type-badge {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 10px;
  border: 1px solid var(--border-color);
}

.type-search {
  color: var(--accent-blue);
}

.type-fetch {
  color: var(--accent-cyan);
}

.type-other {
  color: var(--text-secondary);
}

.badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  border: 1px solid var(--border-color);
}

.badge-success {
  color: var(--accent-green, #2ecc71);
}

.badge-fail {
  color: var(--accent-red);
}

.session-ref {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-muted);
  word-break: break-all;
}

.log-target {
  margin-top: 6px;
  font-size: 13px;
  color: var(--text-secondary);
  word-break: break-word;
}

.log-error {
  margin-top: 4px;
  font-size: 12px;
  color: var(--accent-red);
  word-break: break-word;
}

.log-meta {
  display: flex;
  gap: 16px;
  margin-top: 6px;
  font-size: 11px;
  color: var(--text-muted);
}

.log-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.state-text {
  font-size: 14px;
  color: var(--text-muted);
  padding: 24px;
  text-align: center;
}

.state-text.error-text {
  color: var(--accent-red);
}

.btn-action {
  padding: 4px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.btn-action:hover {
  border-color: var(--accent-blue);
  color: var(--accent-blue);
}

.form-input {
  padding: 6px 10px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
}

.form-input:focus {
  border-color: var(--accent-blue);
}

.btn-secondary {
  padding: 6px 14px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
}

.btn-secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-sm {
  padding: 5px 12px;
  font-size: 12px;
}

.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 24px;
}

.modal-content {
  display: flex;
  flex-direction: column;
  width: 100%;
  max-width: 800px;
  max-height: 80vh;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
  overflow: hidden;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-color);
}

.modal-header h3 {
  font-size: 15px;
  color: var(--text-primary);
  word-break: break-all;
}

.modal-close {
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 22px;
  line-height: 1;
  cursor: pointer;
}

.modal-close:hover {
  color: var(--text-primary);
}

.modal-body {
  padding: 16px;
  overflow-y: auto;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
}

.detail-key {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-muted);
}

.detail-val {
  font-size: 12px;
  color: var(--text-primary);
  word-break: break-word;
}

.detail-block {
  margin-top: 12px;
}

.detail-block-label {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--accent-blue);
  margin-bottom: 6px;
}

.detail-pre {
  margin: 0;
  padding: 10px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 360px;
  overflow: auto;
}

.url-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.url-link {
  color: var(--accent-blue);
  font-size: 12px;
  word-break: break-all;
  text-decoration: none;
}

.url-link:hover {
  text-decoration: underline;
}

@media (max-width: 768px) {
  .toolbar {
    padding: 10px 16px;
  }

  .page-body {
    padding: 12px 16px;
  }

  .log-card {
    flex-direction: column;
    gap: 10px;
  }

  .log-actions {
    width: 100%;
  }
}
</style>
