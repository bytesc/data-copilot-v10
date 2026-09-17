<template>
  <div class="knowledge-page">
    <div class="page-header">
      <div class="page-header-left">
        <router-link to="/" class="back-link">← Back</router-link>
        <h2>Brief Info</h2>
      </div>
    </div>

    <div class="page-body">
      <div v-if="loading" class="loading-text">Loading...</div>
      <div v-else-if="error" class="error-text">{{ error }}</div>
      <template v-else>
        <div v-if="items.length === 0" class="empty-text">No data</div>
        <div v-else class="brief-list">
          <div v-for="item in items" :key="item.attr" class="brief-card">
            <div class="brief-header">
              <span class="brief-attr">{{ item.attr }}</span>
              <button
                v-if="editingAttr !== item.attr"
                class="btn-action btn-edit"
                @click="startEdit(item)"
              >Edit</button>
            </div>
            <div v-if="editingAttr === item.attr" class="brief-edit">
              <textarea
                v-model="editValue"
                class="form-textarea"
                rows="6"
                :placeholder="`Enter ${item.attr} content...`"
              ></textarea>
              <div class="edit-actions">
                <span v-if="editError" class="form-error">{{ editError }}</span>
                <button class="btn-secondary" @click="cancelEdit">Cancel</button>
                <button class="btn-primary" :disabled="saving" @click="save(item.attr)">
                  {{ saving ? 'Saving...' : 'Save' }}
                </button>
              </div>
            </div>
            <div v-else class="brief-value">{{ item.value || '(empty)' }}</div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const API_BASE = '/api/sys-knowledge/brief-info'

const items = ref([])
const loading = ref(true)
const error = ref('')
const editingAttr = ref(null)
const editValue = ref('')
const editError = ref('')
const saving = ref(false)

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

function startEdit(item) {
  editingAttr.value = item.attr
  editValue.value = item.value || ''
  editError.value = ''
}

function cancelEdit() {
  editingAttr.value = null
  editValue.value = ''
  editError.value = ''
}

async function save(attr) {
  saving.value = true
  editError.value = ''
  try {
    const res = await fetch(`${API_BASE}/${encodeURIComponent(attr)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ value: editValue.value }),
    })
    if (!res.ok) {
      const data = await res.json()
      throw new Error(data.detail || `HTTP ${res.status}`)
    }
    cancelEdit()
    await fetchItems()
  } catch (e) {
    editError.value = `Save failed: ${e.message}`
  } finally {
    saving.value = false
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

.brief-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.brief-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
  padding: 16px;
}

.brief-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.brief-attr {
  font-size: 14px;
  font-weight: 600;
  color: var(--accent-cyan);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.brief-value {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}

.brief-edit {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.edit-actions {
  display: flex;
  align-items: center;
  gap: 10px;
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
  min-height: 100px;
}

.form-textarea:focus {
  border-color: var(--accent-blue);
}

.form-error {
  color: var(--accent-red);
  font-size: 13px;
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
}

.btn-edit {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.btn-edit:hover {
  border-color: var(--accent-blue);
  color: var(--accent-blue);
}
</style>