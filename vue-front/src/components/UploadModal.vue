<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal-content">
      <h3>{{ type === 'csv' ? 'Upload CSV File' : 'Upload Document File' }}</h3>
      <div class="modal-body">
        <div class="file-input-group">
          <label class="file-label">
            <input
              type="file"
              :accept="type === 'csv' ? '.csv' : '.txt,.doc,.docx,.pdf'"
              @change="onFileChange"
              :disabled="uploading"
            />
            <span class="file-placeholder">{{ file ? file.name : 'Choose a file...' }}</span>
          </label>
        </div>
        <div class="table-name-group">
          <label>Table name (optional):</label>
          <input
            v-model="tableName"
            type="text"
            placeholder="uploaded_data"
            :disabled="uploading"
          />
        </div>
        <div v-if="uploading" class="uploading-indicator">
          <span class="spinner"></span> Uploading...
        </div>
        <div v-if="result" class="upload-result" :class="result.success ? 'success' : 'error'">
          {{ result.message }}
        </div>
      </div>
      <div class="modal-actions">
        <button class="btn-secondary" @click="$emit('close')" :disabled="uploading">Cancel</button>
        <button class="btn-primary" @click="upload" :disabled="!file || uploading">Upload</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  type: { type: String, required: true },
  serverUrl: { type: String, default: import.meta.env.VITE_SERVER_URL || 'http://127.0.0.1:8009' },
})

const emit = defineEmits(['close'])

const file = ref(null)
const tableName = ref('')
const uploading = ref(false)
const result = ref(null)

function onFileChange(e) {
  file.value = e.target.files[0] || null
}

async function upload() {
  if (!file.value) return
  uploading.value = true
  result.value = null

  try {
    const formData = new FormData()
    formData.append('file', file.value)
    if (tableName.value.trim()) {
      formData.append('table_name', tableName.value.trim())
    }

    const endpoint = props.type === 'csv' ? '/upload-csv/' : '/upload-txt/'
    const res = await fetch(endpoint, {
      method: 'POST',
      body: formData,
    })

    if (res.ok) {
      const data = await res.json()
      if (data.error) {
        result.value = { success: false, message: `Upload failed: ${data.error}` }
      } else {
        result.value = {
          success: true,
          message: `File uploaded successfully! Table: ${data.table_name || tableName.value || 'uploaded_data'}, Rows: ${data.row_count || 'N/A'}`,
        }
      }
    } else {
      result.value = { success: false, message: `Upload failed: HTTP ${res.status}` }
    }
  } catch (e) {
    result.value = { success: false, message: `Upload failed: ${e.message}` }
  } finally {
    uploading.value = false
  }
}
</script>