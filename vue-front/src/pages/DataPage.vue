<template>
  <div class="data-page">
    <div class="data-page-header">
      <router-link to="/" class="back-link">← Back to Chat</router-link>
      <h2>Data Management</h2>
    </div>

    <div class="data-page-content">
      <div class="data-section upload-section">
        <h3 class="section-title">Upload Data</h3>

        <div class="upload-tabs">
          <button
            class="upload-tab"
            :class="{ active: uploadType === 'csv' }"
            @click="uploadType = 'csv'"
          >CSV File</button>
          <button
            class="upload-tab"
            :class="{ active: uploadType === 'doc' }"
            @click="uploadType = 'doc'"
          >Document File</button>
        </div>

        <div class="upload-form">
          <div class="file-input-group">
            <label class="file-label">
              <input
                type="file"
                :accept="uploadType === 'csv' ? '.csv' : '.txt,.doc,.docx,.pdf'"
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

          <button class="btn-primary" @click="upload" :disabled="!file || uploading">
            {{ uploading ? 'Uploading...' : 'Upload' }}
          </button>

          <div v-if="uploading" class="uploading-indicator">
            <span class="spinner"></span> Uploading...
          </div>

          <div v-if="result" class="upload-result" :class="result.success ? 'success' : 'error'">
            {{ result.message }}
          </div>
        </div>
      </div>

      <div class="data-section data-section-stretch">
        <DbOverview :server-url="serverUrl" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import DbOverview from '@/components/DbOverview.vue'

const serverUrl = 'http://127.0.0.1:8009'

const uploadType = ref('csv')
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

    const endpoint = uploadType.value === 'csv' ? '/upload-csv/' : '/upload-txt/'
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

<style scoped>
.data-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.data-page-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 24px;
  border-bottom: 1px solid var(--border-color);
  background: var(--bg-secondary);
}

.data-page-header h2 {
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

.data-page-content {
  flex: 1;
  display: flex;
  gap: 24px;
  padding: 24px;
  overflow-y: auto;
}

.data-section {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
  padding: 20px;
}

.upload-section {
  width: 400px;
  min-width: 400px;
  align-self: flex-start;
}

.data-section-stretch {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
}

.data-section-stretch :deep(.db-overview) {
  flex: 1;
  overflow-y: auto;
  margin-top: 0;
  min-height: 0;
}

.data-section .section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 16px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.upload-tabs {
  display: flex;
  gap: 0;
  margin-bottom: 16px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.upload-tab {
  flex: 1;
  padding: 8px 16px;
  background: var(--bg-tertiary);
  border: none;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.upload-tab.active {
  background: var(--accent-blue);
  color: #fff;
}

.upload-tab:not(:last-child) {
  border-right: 1px solid var(--border-color);
}

.upload-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.upload-form .btn-primary {
  align-self: flex-start;
}

@media (max-width: 768px) {
  .data-page-header {
    padding: 12px 16px;
  }

  .data-page-header h2 {
    font-size: 16px;
  }

  .data-page-content {
    flex-direction: column;
    padding: 12px;
    gap: 12px;
  }

  .upload-section {
    width: 100%;
    min-width: 0;
  }

  .data-section-stretch {
    min-height: 300px;
  }
}
</style>