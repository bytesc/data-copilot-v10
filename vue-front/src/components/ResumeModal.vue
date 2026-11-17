<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal-content">
      <h3>Resume Session</h3>
      <div class="modal-body">
        <div v-if="!selectedSession">
          <div class="manual-input-row">
            <input
              v-model="manualSessionId"
              type="text"
              class="manual-input"
              placeholder="Enter session ID manually..."
              @keyup.enter="resumeManualSession"
            />
            <button
              class="btn-primary btn-sm"
              :disabled="!manualSessionId.trim() || manualLoading"
              @click="resumeManualSession"
            >Go</button>
          </div>
          <div v-if="manualError" class="error-text">{{ manualError }}</div>
          <div class="sessions-list">
            <div v-if="loading" class="loading-text">Loading sessions...</div>
            <div v-else-if="sessions.length === 0" class="empty-text">No sessions found</div>
            <div
              v-for="s in visibleSessions"
              :key="s.session_id"
              class="session-item"
              @click="selectSession(s)"
            >
              <div class="session-id">{{ s.session_id }}</div>
              <div class="session-meta" v-if="s.question">{{ s.question }}</div>
            </div>
          </div>
          <button
            v-if="!loading && sessions.length > RECENT_LIMIT"
            class="btn-secondary view-more-btn"
            @click="viewMoreHistory"
          >View more history</button>
        </div>
        <div v-else class="session-detail">
          <p><strong>Session:</strong> {{ selectedSession.session_id }}</p>
          <p v-if="selectedSession.question"><strong>Question:</strong> {{ selectedSession.question }}</p>
          <div v-if="loadingDetail" class="loading-text">Loading session data...</div>
          <div v-if="detailError" class="error-text">{{ detailError }}</div>
        </div>
      </div>
      <div class="modal-actions">
        <button class="btn-secondary" @click="goBack" v-if="selectedSession">Back</button>
        <button class="btn-secondary" @click="$emit('close')">Cancel</button>
        <button
          class="btn-primary"
          @click="resumeSession"
          :disabled="!selectedSession || loadingDetail"
        >Resume</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { fetchSessions, fetchSessionHistory } from '@/utils/api.js'

const emit = defineEmits(['close', 'resume'])
const router = useRouter()

const RECENT_LIMIT = 5
const sessions = ref([])
const selectedSession = ref(null)
const loading = ref(false)
const loadingDetail = ref(false)
const detailError = ref(null)
const manualSessionId = ref('')
const manualLoading = ref(false)
const manualError = ref(null)

const visibleSessions = computed(() => sessions.value.slice(0, RECENT_LIMIT))

onMounted(async () => {
  loading.value = true
  try {
    sessions.value = await fetchSessions()
  } catch (e) {
    console.error('Failed to fetch sessions:', e)
  } finally {
    loading.value = false
  }
})

function selectSession(s) {
  selectedSession.value = s
  manualError.value = null
}

async function resumeManualSession() {
  const sid = manualSessionId.value.trim()
  if (!sid) return
  manualLoading.value = true
  manualError.value = null
  try {
    const data = await fetchSessionHistory(sid)
    if (!data) {
      manualError.value = 'Session not found or failed to load'
      return
    }
    emit('resume', data)
  } catch (e) {
    manualError.value = `Failed to load session: ${e.message}`
  } finally {
    manualLoading.value = false
  }
}

async function resumeSession() {
  if (!selectedSession.value) return
  loadingDetail.value = true
  detailError.value = null
  try {
    const data = await fetchSessionHistory(selectedSession.value.session_id)
    if (!data) {
      detailError.value = 'Session not found or failed to load'
      return
    }
    emit('resume', data)
  } catch (e) {
    detailError.value = `Failed to load session: ${e.message}`
  } finally {
    loadingDetail.value = false
  }
}

function goBack() {
  selectedSession.value = null
  detailError.value = null
}

function viewMoreHistory() {
  emit('close')
  router.push('/history')
}
</script>

<style scoped>
.view-more-btn {
  display: block;
  width: 100%;
  margin-top: 10px;
}
</style>