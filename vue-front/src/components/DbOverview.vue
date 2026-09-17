<template>
  <div class="db-overview">
    <h3 class="section-title" @click="collapsed = !collapsed">Data View {{ collapsed ? '▶' : '▼' }}</h3>
    <div v-show="!collapsed">
      <div v-if="loading" class="loading-text">Loading...</div>
      <div v-else-if="error" class="error-text">{{ error }}</div>
      <div v-else class="tables-list">
        <div v-for="table in tables" :key="table.name" class="table-item">
          <details class="table-details">
            <summary class="table-name">
              <span>📊 {{ table.name }}</span>
              <span class="delete-btn" @click.prevent.stop="promptDelete(table)">✕</span>
            </summary>
            <div class="table-content">
              <p v-if="table.comment" class="table-comment">{{ table.comment }}</p>
              <div v-if="table.columns?.length" class="columns-section">
                <h4>Columns</h4>
                <table class="columns-table">
                  <thead>
                    <tr><th>Column</th><th>Comment</th></tr>
                  </thead>
                  <tbody>
                    <tr v-for="col in table.columns" :key="col.name">
                      <td>{{ col.name }}</td>
                      <td>{{ col.comment || '' }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </details>
        </div>
      </div>
    </div>

    <div v-if="deletingTable" class="modal-overlay" @click.self="cancelDelete">
      <div class="modal-content confirm-modal">
        <h3>Delete Table</h3>
        <div class="modal-body">
          <p>Type <strong>{{ deletingTable }}</strong> to confirm deletion:</p>
          <input
            v-model="confirmText"
            type="text"
            class="form-input confirm-input"
            :placeholder="`Type '${deletingTable}' to confirm`"
            @keyup.enter="executeDelete"
          />
          <div v-if="deleteError" class="form-error">{{ deleteError }}</div>
        </div>
        <div class="modal-actions">
          <button class="btn-secondary" @click="cancelDelete">Cancel</button>
          <button
            class="btn-danger"
            :disabled="confirmText !== deletingTable || deleting"
            @click="executeDelete"
          >
            {{ deleting ? 'Deleting...' : 'Delete' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const props = defineProps({
  serverUrl: { type: String, default: import.meta.env.VITE_SERVER_URL || 'http://127.0.0.1:8009' },
})

const tables = ref([])
const loading = ref(false)
const error = ref(null)
const collapsed = ref(false)

const deletingTable = ref(null)
const confirmText = ref('')
const deleteError = ref('')
const deleting = ref(false)

onMounted(async () => {
  await loadTables()
})

async function loadTables() {
  loading.value = true
  try {
    const res = await fetch('/api/db-overview/')
    if (res.ok) {
      const data = await res.json()
      tables.value = data.tables || []
    }
  } catch {
  } finally {
    loading.value = false
  }
}

function promptDelete(table) {
  deletingTable.value = table.name
  confirmText.value = ''
  deleteError.value = ''
}

function cancelDelete() {
  deletingTable.value = null
  confirmText.value = ''
  deleteError.value = ''
}

async function executeDelete() {
  if (confirmText.value !== deletingTable.value) return
  deleting.value = true
  deleteError.value = ''
  try {
    const res = await fetch(`/api/table/${encodeURIComponent(deletingTable.value)}`, { method: 'DELETE' })
    if (!res.ok) {
      const data = await res.json()
      throw new Error(data.detail || `HTTP ${res.status}`)
    }
    tables.value = tables.value.filter(t => t.name !== deletingTable.value)
    cancelDelete()
  } catch (e) {
    deleteError.value = e.message
  } finally {
    deleting.value = false
  }
}
</script>

<style scoped>
.delete-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  font-size: 11px;
  border-radius: 50%;
  background: var(--bg-tertiary);
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.2s;
  margin-left: auto;
  flex-shrink: 0;
}

.delete-btn:hover {
  background: var(--accent-red);
  color: #fff;
}

.table-name {
  display: flex;
  align-items: center;
  gap: 8px;
}

.confirm-modal {
  width: 400px;
}

.confirm-input {
  width: 100%;
  margin-top: 8px;
}

.form-input {
  padding: 8px 12px;
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

.form-error {
  color: var(--accent-red);
  font-size: 13px;
  margin-top: 6px;
}

.btn-danger {
  padding: 8px 20px;
  background: var(--accent-red);
  border: none;
  border-radius: var(--radius-sm);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.btn-danger:hover:not(:disabled) {
  opacity: 0.85;
}

.btn-danger:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>