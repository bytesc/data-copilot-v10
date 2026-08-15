<template>
  <div class="db-overview">
    <h3 class="section-title">Data View</h3>
    <div v-if="loading" class="loading-text">Loading...</div>
    <div v-else-if="error" class="error-text">{{ error }}</div>
    <div v-else class="tables-list">
      <div v-for="table in tables" :key="table.name" class="table-item">
        <details class="table-details">
          <summary class="table-name">📊 {{ table.name }}</summary>
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
</template>

<script setup>
import { ref, onMounted } from 'vue'

const props = defineProps({
  serverUrl: { type: String, default: 'http://127.0.0.1:8009' },
})

const tables = ref([])
const loading = ref(false)
const error = ref(null)

onMounted(async () => {
  loading.value = true
  try {
    const res = await fetch('/api/db-overview/')
    if (res.ok) {
      const data = await res.json()
      tables.value = data.tables || []
    } else if (res.status === 404) {
      error.value = null
    }
  } catch (e) {
    error.value = null
  } finally {
    loading.value = false
  }
})
</script>