<template>
  <div class="knowledge-page">
    <div class="page-header">
      <div class="page-header-left">
        <router-link to="/" class="back-link">← Back</router-link>
        <h2>Table &amp; Column Comments</h2>
      </div>
    </div>

    <div class="page-body">
      <div v-if="loading" class="loading-text">Loading...</div>
      <div v-else-if="error" class="error-text">{{ error }}</div>
      <template v-else>
        <div v-if="tables.length === 0" class="empty-text">No tables</div>
        <div v-else class="table-list">
          <div v-for="tbl in tables" :key="tbl.name" class="table-card">
            <div class="table-card-header" @click="toggleCollapse(tbl.name)">
              <span class="collapse-arrow">{{ isCollapsed(tbl.name) ? '▶' : '▼' }}</span>
              <span class="table-name-label">📊 {{ tbl.name }}</span>
              <span class="table-col-count">{{ tbl.columns.length }} columns</span>
            </div>

            <div v-show="!isCollapsed(tbl.name)">
              <div class="expanded-header">
                <button
                  v-if="editingTable !== tbl.name"
                  class="btn-action btn-edit"
                  @click="startEditTable(tbl)"
                >Edit Table Comment</button>
                <button class="btn-action btn-export" @click="exportCsv(tbl.name)">Export CSV</button>
                <button class="btn-action btn-import" @click="triggerImport(tbl.name)">Import CSV</button>
                <input
                  ref="fileInputs"
                  type="file"
                  accept=".csv"
                  style="display:none"
                  :data-table="tbl.name"
                  @change="importCsv($event, tbl.name)"
                />
              </div>
              <div v-if="editingTable === tbl.name" class="inline-edit">
                <textarea v-model="editTableComment" class="form-textarea" rows="2" placeholder="Table comment..."></textarea>
                <div class="edit-actions">
                  <span v-if="editError" class="form-error">{{ editError }}</span>
                  <button class="btn-secondary btn-sm" @click="cancelEditTable">Cancel</button>
                  <button class="btn-primary btn-sm" :disabled="savingTable" @click="saveTableComment(tbl.name)">
                    {{ savingTable ? 'Saving...' : 'Save' }}
                  </button>
                </div>
              </div>
              <div v-else class="table-comment-display">{{ tbl.comment || '(no comment)' }}</div>

              <div class="columns-section">
                <div v-for="col in tbl.columns" :key="col.name" class="column-row">
                  <div class="column-info">
                    <span class="col-name">{{ col.name }}</span>
                    <span class="col-type">{{ col.type }}</span>
                  </div>
                  <div class="column-comment-area">
                    <div v-if="editingColumn !== col.name + tbl.name" class="column-comment">
                      <span class="col-comment-text">{{ col.comment || '(no comment)' }}</span>
                      <button class="btn-action btn-edit btn-xs" @click="startEditColumn(tbl, col)">Edit</button>
                    </div>
                    <div v-else class="inline-edit column-edit">
                      <input v-model="editColComment" type="text" class="form-input col-comment-input" placeholder="Column comment..." />
                      <div class="edit-actions">
                        <span v-if="colEditError" class="form-error">{{ colEditError }}</span>
                        <button class="btn-secondary btn-xs" @click="cancelEditColumn">Cancel</button>
                        <button class="btn-primary btn-xs" :disabled="savingCol" @click="saveColumnComment(tbl.name, col.name)">
                          {{ savingCol ? 'Saving...' : 'Save' }}
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const API_BASE = '/api/comment-manage'

const tables = ref([])
const loading = ref(true)
const error = ref('')

const editingTable = ref(null)
const editTableComment = ref('')
const savingTable = ref(false)
const editError = ref('')

const collapsedTables = ref(new Set())

onMounted(() => {
  fetchTables().then(() => {
    const s = new Set()
    tables.value.forEach(t => s.add(t.name))
    collapsedTables.value = s
  })
})

function toggleCollapse(name) {
  const s = new Set(collapsedTables.value)
  if (s.has(name)) s.delete(name); else s.add(name)
  collapsedTables.value = s
}

function isCollapsed(name) {
  return collapsedTables.value.has(name)
}

const editingColumn = ref(null)
const editColComment = ref('')
const savingCol = ref(false)
const colEditError = ref('')

async function fetchTables() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetch(`${API_BASE}/`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    tables.value = data.tables || []
  } catch (e) {
    error.value = `Load failed: ${e.message}`
  } finally {
    loading.value = false
  }
}

function startEditTable(tbl) {
  editingTable.value = tbl.name
  editTableComment.value = tbl.comment || ''
  cancelEditColumn()
}

function cancelEditTable() {
  editingTable.value = null
  editTableComment.value = ''
  editError.value = ''
}

async function saveTableComment(tableName) {
  savingTable.value = true
  editError.value = ''
  try {
    const res = await fetch(`${API_BASE}/${encodeURIComponent(tableName)}/table-comment`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ comment: editTableComment.value }),
    })
    if (!res.ok) {
      const data = await res.json()
      throw new Error(data.detail || `HTTP ${res.status}`)
    }
    cancelEditTable()
    await fetchTables()
  } catch (e) {
    editError.value = `Save failed: ${e.message}`
  } finally {
    savingTable.value = false
  }
}

function startEditColumn(tbl, col) {
  editingColumn.value = col.name + tbl.name
  editColComment.value = col.comment || ''
  cancelEditTable()
}

function cancelEditColumn() {
  editingColumn.value = null
  editColComment.value = ''
  colEditError.value = ''
}

const fileInputs = ref([])

function exportCsv(tableName) {
  const url = `/api/comment-manage/${encodeURIComponent(tableName)}/export-csv`
  const a = document.createElement('a')
  a.href = url
  a.download = `${tableName}_comments.csv`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

function triggerImport(tableName) {
  const inputs = fileInputs.value
  if (!inputs || !inputs.length) return
  for (const el of inputs) {
    if (el.dataset.table === tableName) {
      el.value = ''
      el.click()
      break
    }
  }
}

async function importCsv(event, tableName) {
  const file = event.target.files?.[0]
  if (!file) return
  const formData = new FormData()
  formData.append('file', file)
  try {
    const res = await fetch(`/api/comment-manage/${encodeURIComponent(tableName)}/import-csv`, {
      method: 'POST',
      body: formData,
    })
    if (!res.ok) {
      const data = await res.json()
      throw new Error(data.detail || `HTTP ${res.status}`)
    }
    const result = await res.json()
    if (!result.success) {
      alert(`Import failed:\n${result.error}`)
      return
    }
    alert(`Import successful!\nTable comment updated: ${result.table_comment_updated}\nColumns updated: ${result.columns_updated}`)
    await fetchTables()
  } catch (e) {
    alert(`Import failed: ${e.message}`)
  }
}

async function saveColumnComment(tableName, columnName) {
  savingCol.value = true
  colEditError.value = ''
  try {
    const res = await fetch(`${API_BASE}/${encodeURIComponent(tableName)}/column/${encodeURIComponent(columnName)}/comment`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ comment: editColComment.value }),
    })
    if (!res.ok) {
      const data = await res.json()
      throw new Error(data.detail || `HTTP ${res.status}`)
    }
    cancelEditColumn()
    await fetchTables()
  } catch (e) {
    colEditError.value = `Save failed: ${e.message}`
  } finally {
    savingCol.value = false
  }
}

</script>

<style scoped>
.knowledge-page {
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

.page-body {
  flex: 1;
  padding: 16px 24px;
  overflow-y: auto;
}

.table-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.table-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
  padding: 16px;
}

.table-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 0;
  cursor: pointer;
  user-select: none;
}

.table-card-header:hover {
  opacity: 0.85;
}

.expanded-header {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  margin-bottom: 8px;
  margin-top: 8px;
}

.collapse-arrow {
  font-size: 10px;
  color: var(--text-muted);
  width: 12px;
  flex-shrink: 0;
}

.table-col-count {
  font-size: 11px;
  color: var(--text-muted);
  margin-right: auto;
}

.table-name-label {
  font-size: 15px;
  font-weight: 700;
  color: var(--accent-cyan);
}

.table-comment-display {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 12px;
  padding: 6px 10px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-sm);
  line-height: 1.4;
}

.columns-section {
  border-top: 1px solid var(--border-color);
  padding-top: 10px;
}

.column-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 6px 0;
  border-bottom: 1px solid var(--border-color);
}

.column-row:last-child {
  border-bottom: none;
}

.column-info {
  min-width: 200px;
  flex-shrink: 0;
}

.col-name {
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--text-primary);
  font-weight: 600;
  margin-right: 8px;
}

.col-type {
  font-size: 11px;
  color: var(--text-muted);
  font-family: var(--font-mono);
}

.column-comment-area {
  flex: 1;
  min-width: 0;
}

.column-comment {
  display: flex;
  align-items: center;
  gap: 8px;
}

.col-comment-text {
  font-size: 13px;
  color: var(--text-secondary);
  flex: 1;
  word-break: break-word;
}

.inline-edit {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.column-edit {
  flex: 1;
}

.col-comment-input {
  width: 100%;
}

.edit-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.form-textarea {
  width: 100%;
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
  font-family: var(--font-sans);
  resize: vertical;
  min-height: 40px;
}

.form-textarea:focus,
.form-input:focus {
  border-color: var(--accent-blue);
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

.form-error {
  color: var(--accent-red);
  font-size: 12px;
}

.loading-text {
  font-size: 14px;
  color: var(--text-muted);
  padding: 24px;
  text-align: center;
}

.error-text {
  font-size: 14px;
  color: var(--accent-red);
  padding: 24px;
  text-align: center;
}

.empty-text {
  font-size: 14px;
  color: var(--text-muted);
  padding: 40px;
  text-align: center;
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

.btn-edit:hover {
  border-color: var(--accent-blue);
  color: var(--accent-blue);
}

.btn-export:hover {
  border-color: var(--accent-green, #2ecc71);
  color: var(--accent-green, #2ecc71);
}

.btn-import:hover {
  border-color: var(--accent-orange, #e67e22);
  color: var(--accent-orange, #e67e22);
}



.btn-xs {
  padding: 3px 8px;
  font-size: 11px;
}

.btn-sm {
  padding: 5px 12px;
  font-size: 12px;
}
</style>