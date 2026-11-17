<template>
  <div class="history-page">
    <div class="page-header">
      <div class="page-header-left">
        <router-link to="/" class="back-link">← Back to Chat</router-link>
        <h2>History</h2>
      </div>
      <button class="btn-secondary btn-sm" :disabled="loading" @click="loadSessions">
        {{ loading ? 'Loading...' : 'Refresh' }}
      </button>
    </div>

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
      <input
        v-model="search"
        type="text"
        class="form-input search-input"
        placeholder="Search by session ID or question..."
      />
    </div>

    <div class="page-body">
      <div v-if="loading && sessions.length === 0" class="state-text">Loading...</div>
      <div v-else-if="error" class="state-text error-text">{{ error }}</div>
      <div v-else-if="filteredSessions.length === 0" class="state-text">No conversations found</div>
      <div v-else class="session-list">
        <div
          v-for="s in filteredSessions"
          :key="s.session_id"
          class="session-card"
          :class="{ deleted: isDeleted(s) }"
        >
          <div class="session-main">
            <div class="session-top">
              <span class="session-id">{{ s.session_id }}</span>
              <span v-if="isDeleted(s)" class="badge badge-deleted">Deleted</span>
              <span v-else class="badge badge-active">{{ s.status || 'active' }}</span>
            </div>
            <div class="session-question">{{ s.question || '(no question)' }}</div>
            <div class="session-meta">
              <span v-if="s.total_tokens">Tokens: {{ s.total_tokens }}</span>
              <span v-if="s.updated_at">Updated: {{ formatTime(s.updated_at) }}</span>
            </div>
          </div>
          <div class="session-actions">
            <button class="btn-action" @click="viewSession(s)">View</button>
            <button class="btn-action btn-resume" @click="onResume(s)">Resume</button>
            <button
              v-if="isDeleted(s)"
              class="btn-action btn-restore"
              :disabled="busyId === s.session_id"
              @click="onRestore(s)"
            >Restore</button>
            <button
              v-else
              class="btn-action btn-delete"
              :disabled="busyId === s.session_id"
              @click="onDelete(s)"
            >Delete</button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="detailSession" class="modal-overlay" @click.self="closeDetail">
      <div class="modal-content">
        <div class="modal-header">
          <h3>{{ detailSession.session_id }}</h3>
          <button class="modal-close" @click="closeDetail">×</button>
        </div>
        <div class="modal-body">
          <div v-if="detailLoading" class="state-text">Loading conversation...</div>
          <div v-else-if="detailError" class="state-text error-text">{{ detailError }}</div>
          <div v-else-if="detailMessages.length === 0" class="state-text">No messages recorded</div>
          <div v-else class="message-list">
            <div
              v-for="(m, i) in detailMessages"
              :key="i"
              class="history-entry"
              :class="entryClass(m)"
            >
              <div class="entry-label">{{ entryLabel(m) }}</div>
              <pre class="history-json">{{ formatJson(m) }}</pre>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  fetchSessions,
  fetchSessionHistory,
  deleteSession,
  restoreSession,
} from '@/utils/api.js'
import { showErrorToast, showSuccessToast } from '@/utils/toast.js'

const router = useRouter()

const filters = [
  { value: 'active', label: 'Active' },
  { value: 'deleted', label: 'Deleted' },
  { value: 'all', label: 'All' },
]

const sessions = ref([])
const loading = ref(false)
const error = ref('')
const filter = ref('active')
const search = ref('')
const busyId = ref('')

const detailSession = ref(null)
const detailMessages = ref([])
const detailLoading = ref(false)
const detailError = ref('')

function isDeleted(s) {
  return !!s.deleted
}

const filteredSessions = computed(() => {
  const term = search.value.trim().toLowerCase()
  return sessions.value.filter((s) => {
    if (filter.value === 'active' && isDeleted(s)) return false
    if (filter.value === 'deleted' && !isDeleted(s)) return false
    if (term) {
      const id = (s.session_id || '').toLowerCase()
      const q = (s.question || '').toLowerCase()
      if (!id.includes(term) && !q.includes(term)) return false
    }
    return true
  })
})

function formatTime(value) {
  if (!value) return ''
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return String(value)
  return d.toLocaleString()
}

async function loadSessions() {
  loading.value = true
  error.value = ''
  try {
    sessions.value = await fetchSessions(200, true)
  } catch (e) {
    error.value = `Load failed: ${e.message}`
  } finally {
    loading.value = false
  }
}

async function onDelete(s) {
  busyId.value = s.session_id
  try {
    await deleteSession(s.session_id)
    s.deleted = 1
    showSuccessToast('Conversation deleted')
  } catch (e) {
    showErrorToast(`Delete failed: ${e.message}`)
  } finally {
    busyId.value = ''
  }
}

async function onRestore(s) {
  busyId.value = s.session_id
  try {
    await restoreSession(s.session_id)
    s.deleted = 0
    showSuccessToast('Conversation restored')
  } catch (e) {
    showErrorToast(`Restore failed: ${e.message}`)
  } finally {
    busyId.value = ''
  }
}

function onResume(s) {
  const target = router.resolve({ path: '/', query: { resume: s.session_id } })
  window.open(target.href, '_blank', 'noopener')
}

async function viewSession(s) {
  detailSession.value = s
  detailMessages.value = []
  detailError.value = ''
  detailLoading.value = true
  try {
    const data = await fetchSessionHistory(s.session_id)
    detailMessages.value = data?.conversation_history || []
  } catch (e) {
    detailError.value = `Load failed: ${e.message}`
  } finally {
    detailLoading.value = false
  }
}

function closeDetail() {
  detailSession.value = null
  detailMessages.value = []
  detailError.value = ''
}

function formatJson(value) {
  try {
    return JSON.stringify(value, null, 2)
  } catch (_) {
    return String(value)
  }
}

function entryClass(m) {
  const role = m.role || ''
  const type = m.type || ''
  const phase = m.phase || ''
  if (role === 'user' || type === 'user') return 'entry-user'
  if (type === 'error') return 'entry-error'
  if (phase === 'think') return 'entry-think'
  if (phase === 'observe') return 'entry-observe'
  if (phase === 'action_decision' || phase === 'act' || type === 'act') return 'entry-act'
  return 'entry-default'
}

function entryLabel(m) {
  const role = m.role || ''
  const type = m.type || ''
  const phase = m.phase || ''
  const action = m.action ? ` · ${m.action}` : ''
  const parts = [role || 'entry']
  if (type) parts.push(type)
  if (phase) parts.push(phase)
  return parts.join(' · ') + action
}

onMounted(loadSessions)
</script>

<style scoped>
.history-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 24px;
  border-bottom: 1px solid var(--border-color);
  background: var(--bg-secondary);
  flex-shrink: 0;
}

.page-header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.page-header-left h2 {
  font-size: 18px;
  color: var(--text-primary);
}

.back-link {
  color: var(--accent-blue);
  text-decoration: none;
  font-size: 14px;
  white-space: nowrap;
}

.back-link:hover {
  text-decoration: underline;
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

.session-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.session-card {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
}

.session-card.deleted {
  opacity: 0.65;
}

.session-main {
  min-width: 0;
  flex: 1;
}

.session-top {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.session-id {
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--text-primary);
  font-weight: 600;
}

.badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  border: 1px solid var(--border-color);
}

.badge-active {
  color: var(--accent-green, #2ecc71);
}

.badge-deleted {
  color: var(--accent-red);
}

.session-question {
  margin-top: 6px;
  font-size: 13px;
  color: var(--text-secondary);
  word-break: break-word;
}

.session-meta {
  display: flex;
  gap: 16px;
  margin-top: 6px;
  font-size: 11px;
  color: var(--text-muted);
}

.session-actions {
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

.btn-action:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-resume:hover:not(:disabled) {
  border-color: var(--accent-blue);
  color: var(--accent-blue);
}

.btn-restore:hover:not(:disabled) {
  border-color: var(--accent-green, #2ecc71);
  color: var(--accent-green, #2ecc71);
}

.btn-delete:hover:not(:disabled) {
  border-color: var(--accent-red);
  color: var(--accent-red);
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
  font-family: var(--font-mono);
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

.message-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.history-entry {
  border: 1px solid var(--border-color);
  border-left-width: 3px;
  border-left-color: var(--accent-blue);
  border-radius: var(--radius-sm);
  padding: 10px 12px;
  background: var(--bg-tertiary);
}

.history-entry.entry-user,
.history-entry.entry-error {
  border-left-color: var(--accent-red);
}

.history-entry.entry-act {
  border-left-color: var(--accent-green);
}

.history-entry.entry-think {
  border-left-color: var(--accent-orange);
}

.history-entry.entry-observe {
  border-left-color: var(--accent-cyan);
}

.entry-label {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--accent-blue);
  margin-bottom: 6px;
  word-break: break-word;
}

.history-entry.entry-user .entry-label,
.history-entry.entry-error .entry-label {
  color: var(--accent-red);
}

.history-entry.entry-act .entry-label {
  color: var(--accent-green);
}

.history-entry.entry-think .entry-label {
  color: var(--accent-orange);
}

.history-entry.entry-observe .entry-label {
  color: var(--accent-cyan);
}

.history-json {
  margin: 0;
  padding: 0;
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-x: auto;
}

@media (max-width: 768px) {
  .page-header {
    padding: 12px 16px;
  }

  .page-header-left h2 {
    font-size: 16px;
  }

  .toolbar {
    padding: 10px 16px;
  }

  .page-body {
    padding: 12px 16px;
  }

  .session-card {
    flex-direction: column;
    gap: 10px;
  }

  .session-actions {
    width: 100%;
  }
}
</style>
