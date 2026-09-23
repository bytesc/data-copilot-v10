<template>
  <div class="knowledge-page">
    <div class="page-header">
      <div class="page-header-left">
        <router-link to="/" class="back-link">← Back</router-link>
        <h2>Data Query Guide</h2>
      </div>
      <button class="btn-primary" @click="openCreate">+ New</button>
    </div>

    <div class="page-body">
      <div v-if="loading" class="loading-text">Loading...</div>
      <div v-else-if="error" class="error-text">{{ error }}</div>
      <template v-else>
        <div class="search-bar">
          <input v-model="searchQuery" type="text" placeholder="Search key..." class="search-input" />
        </div>
        <div v-if="filteredItems.length === 0" class="empty-text">No data</div>
        <table v-else class="data-table">
          <thead>
            <tr>
              <th class="col-id">ID</th>
              <th class="col-key">Key</th>
              <th class="col-value">Value</th>
              <th class="col-actions">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in filteredItems" :key="item.id">
              <td class="col-id">{{ item.id }}</td>
              <td class="col-key">{{ item.key }}</td>
              <td class="col-value">
                <div class="value-preview">{{ item.value }}</div>
              </td>
              <td class="col-actions">
                <button class="btn-action btn-edit" @click="openEdit(item)">Edit</button>
                <button class="btn-action btn-delete" @click="confirmDelete(item)">Delete</button>
              </td>
            </tr>
          </tbody>
        </table>
      </template>
    </div>

    <div v-if="showForm" class="modal-overlay" @click.self="closeForm">
      <div class="modal-content">
        <h3>{{ editingItem ? 'Edit' : 'New' }} Data Query Guide</h3>
        <div class="modal-body">
          <div class="form-group">
            <label>Key</label>
            <input v-model="formKey" type="text" class="form-input" placeholder="Guide key" />
          </div>
          <div class="form-group">
            <label>Value</label>
            <textarea v-model="formValue" class="form-textarea" rows="6" placeholder="Guide content (SQL query instructions, etc.)"></textarea>
          </div>
          <div v-if="formError" class="form-error">{{ formError }}</div>
        </div>
        <div class="modal-actions">
          <button class="btn-secondary" @click="closeForm">Cancel</button>
          <button class="btn-primary" :disabled="saving" @click="save">{{ saving ? 'Saving...' : 'Save' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'

const API_BASE = '/api/sys-knowledge/db-query-guide'

const items = ref([])
const loading = ref(true)
const error = ref('')
const searchQuery = ref('')

const showForm = ref(false)
const editingItem = ref(null)
const formKey = ref('')
const formValue = ref('')
const formError = ref('')
const saving = ref(false)

const filteredItems = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return items.value
  return items.value.filter(i => i.key.toLowerCase().includes(q))
})

async function fetchItems() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetch(`${API_BASE}/`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    items.value = await res.json()
  } catch (e) {
    error.value = `Load failed: ${e.message}`
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingItem.value = null
  formKey.value = ''
  formValue.value = ''
  formError.value = ''
  showForm.value = true
}

function openEdit(item) {
  editingItem.value = item
  formKey.value = item.key
  formValue.value = item.value
  formError.value = ''
  showForm.value = true
}

function closeForm() {
  showForm.value = false
  editingItem.value = null
  formKey.value = ''
  formValue.value = ''
  formError.value = ''
}

async function save() {
  if (!formKey.value.trim()) {
    formError.value = 'Key is required'
    return
  }
  saving.value = true
  formError.value = ''
  try {
    const body = { key: formKey.value.trim(), value: formValue.value }
    let res
    if (editingItem.value) {
      res = await fetch(`${API_BASE}/${editingItem.value.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
    } else {
      res = await fetch(`${API_BASE}/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
    }
    if (!res.ok) {
      const data = await res.json()
      throw new Error(data.detail || `HTTP ${res.status}`)
    }
    closeForm()
    await fetchItems()
  } catch (e) {
    formError.value = `Save failed: ${e.message}`
  } finally {
    saving.value = false
  }
}

async function confirmDelete(item) {
  if (!confirm(`Delete "${item.key}"?`)) return
  try {
    const res = await fetch(`${API_BASE}/${item.id}`, { method: 'DELETE' })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    await fetchItems()
  } catch (e) {
    error.value = `Delete failed: ${e.message}`
  }
}

onMounted(fetchItems)
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

.search-bar {
  margin-bottom: 12px;
}

.search-input {
  width: 100%;
  max-width: 360px;
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
}

.search-input:focus {
  border-color: var(--accent-blue);
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.data-table th,
.data-table td {
  border: 1px solid var(--border-color);
  padding: 8px 12px;
  text-align: left;
}

.data-table th {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  font-weight: 600;
  white-space: nowrap;
}

.data-table tbody tr:hover {
  background: var(--bg-hover);
}

.col-id { width: 60px; }
.col-key { width: 220px; }
.col-actions { width: 130px; white-space: nowrap; }

.value-preview {
  max-height: 60px;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  word-break: break-word;
  line-height: 1.4;
}

.btn-action {
  padding: 4px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  font-size: 12px;
  cursor: pointer;
  margin-right: 4px;
  transition: all 0.2s;
}

.btn-edit {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.btn-edit:hover {
  border-color: var(--accent-blue);
  color: var(--accent-blue);
}

.btn-delete {
  background: var(--bg-tertiary);
  color: var(--accent-red);
}

.btn-delete:hover {
  border-color: var(--accent-red);
  background: rgba(217, 83, 79, 0.1);
}

.form-group {
  margin-bottom: 14px;
}

.form-group label {
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.form-input,
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
}

.form-input:focus,
.form-textarea:focus {
  border-color: var(--accent-blue);
}

.form-textarea {
  resize: vertical;
  min-height: 100px;
}

.form-error {
  color: var(--accent-red);
  font-size: 13px;
  padding: 8px 0;
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

@media (max-width: 768px) {
  .page-header { padding: 12px 16px; }
  .page-header-left h2 { font-size: 16px; }
  .page-body { padding: 12px 16px; }
  .data-table, .data-table thead, .data-table tbody, .data-table tr, .data-table th, .data-table td { display: block; }
  .data-table thead { display: none; }
  .data-table tr { padding: 10px; border: 1px solid var(--border-color); border-radius: var(--radius-sm); margin-bottom: 8px; background: var(--bg-secondary); }
  .data-table td { border: none; padding: 4px 0; }
  .col-id, .col-key, .col-value, .col-actions { width: auto; }
  .col-id::before { content: "ID: "; font-weight: 600; color: var(--text-muted); }
  .col-key::before { content: "Key: "; font-weight: 600; color: var(--text-muted); }
  .col-value::before { content: "Value: "; font-weight: 600; color: var(--text-muted); display: block; margin-bottom: 4px; }
  .col-actions { display: flex; gap: 6px; margin-top: 8px; }
  .search-input { max-width: 100%; }
  .modal-content { width: 95vw; max-width: 95vw; margin: 0 10px; }
}
</style>