<template>
  <div class="knowledge-page">
    <div class="page-header">
      <div class="page-header-left">
        <router-link to="/" class="back-link">← Back</router-link>
        <h2>Guide Management</h2>
      </div>
    </div>

    <nav class="guide-tabs">
      <button
        v-for="tab in guideTabs"
        :key="tab.key"
        :class="['guide-tab', { active: activeTab === tab.key }]"
        @click="switchTab(tab.key)"
      >
        {{ tab.label }}
      </button>
    </nav>

    <div class="page-body">
      <div class="tab-header">
        <h3>{{ currentTab?.label }}</h3>
        <button class="btn-primary" @click="openCreate">+ New</button>
      </div>

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

    <div v-if="showDeleteConfirm" class="modal-overlay">
      <div class="modal-content modal-sm">
        <h3>Confirm Delete</h3>
        <div class="modal-body">
          <p>Delete "{{ deleteTarget?.key }}"?</p>
        </div>
        <div class="modal-actions">
          <button class="btn-secondary" @click="cancelDelete">Cancel</button>
          <button class="btn-danger" @click="doDelete">Delete</button>
        </div>
      </div>
    </div>

    <div v-if="showForm" class="modal-overlay">
      <div class="modal-content">
        <h3>{{ editingItem ? 'Edit' : 'New' }} {{ currentTab?.label }}</h3>
        <div class="modal-body">
          <div class="form-group">
            <label>Key</label>
            <input v-model="formKey" type="text" class="form-input" placeholder="Guide key" />
          </div>
          <div class="form-group">
            <label>Value</label>
            <textarea v-model="formValue" class="form-textarea" rows="6" placeholder="Guide content"></textarea>
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
import { ref, computed, onMounted, watch } from 'vue'

const guideTabs = [
  { key: 'code-guide', label: 'Code Guide' },
  { key: 'graph-code-guide', label: 'Graph Code Guide' },
  { key: 'think-guide', label: 'Think Guide' },
  { key: 'doc-guide', label: 'Doc Guide' },
]

const activeTab = ref('code-guide')
const currentTab = computed(() => guideTabs.find(t => t.key === activeTab.value))
const apiBase = computed(() => `/api/sys-knowledge/${activeTab.value}`)

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

const showDeleteConfirm = ref(false)
const deleteTarget = ref(null)

const filteredItems = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return items.value
  return items.value.filter(i => i.key.toLowerCase().includes(q))
})

function switchTab(key) {
  activeTab.value = key
  searchQuery.value = ''
  closeForm()
}

async function fetchItems() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetch(`${apiBase.value}/`)
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
      res = await fetch(`${apiBase.value}/${editingItem.value.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
    } else {
      res = await fetch(`${apiBase.value}/`, {
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

function confirmDelete(item) {
  deleteTarget.value = item
  showDeleteConfirm.value = true
}

async function doDelete() {
  if (!deleteTarget.value) return
  try {
    const res = await fetch(`${apiBase.value}/${deleteTarget.value.id}`, { method: 'DELETE' })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    await fetchItems()
  } catch (e) {
    error.value = `Delete failed: ${e.message}`
  } finally {
    showDeleteConfirm.value = false
    deleteTarget.value = null
  }
}

function cancelDelete() {
  showDeleteConfirm.value = false
  deleteTarget.value = null
}

watch(activeTab, fetchItems)
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

.guide-tabs {
  display: flex;
  gap: 2px;
  padding: 0 24px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.guide-tab {
  padding: 10px 16px;
  color: var(--text-secondary);
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.guide-tab:hover {
  color: var(--text-primary);
  background: var(--bg-hover);
}

.guide-tab.active {
  color: var(--accent-blue);
  border-bottom-color: var(--accent-blue);
}

.tab-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.tab-header h3 {
  font-size: 16px;
  color: var(--text-primary);
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

.btn-primary {
  padding: 8px 16px;
  background: var(--accent-blue);
  color: #fff;
  border: none;
  border-radius: var(--radius-sm);
  font-size: 13px;
  cursor: pointer;
  transition: opacity 0.2s;
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-danger {
  padding: 8px 16px;
  background: var(--accent-red);
  color: #fff;
  border: none;
  border-radius: var(--radius-sm);
  font-size: 13px;
  cursor: pointer;
}

.btn-danger:hover {
  opacity: 0.85;
}

.btn-secondary {
  padding: 8px 16px;
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  font-size: 13px;
  cursor: pointer;
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

.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: var(--bg-primary);
  border-radius: var(--radius-md);
  width: 560px;
  max-width: 90vw;
  max-height: 80vh;
  overflow-y: auto;
}

.modal-sm {
  width: 400px;
}

.modal-content h3 {
  font-size: 16px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-color);
  color: var(--text-primary);
}

.modal-body {
  padding: 20px;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 20px;
  border-top: 1px solid var(--border-color);
}
</style>