<template>
  <div class="modal-overlay" @click.self="onOverlayClick">
    <div class="modal-container">
      <!-- Recovery: pick existing file -->
      <template v-if="step === 'pick'">
        <div class="modal-header">
          <h3>📐 Document Generation</h3>
          <p class="modal-subtitle">Resume from a saved draft or start fresh.</p>
        </div>
        <div class="modal-body pick-body">
          <div v-if="availableFiles.length === 0 && !loadingFiles" class="empty-text">No saved files found.</div>
          <div v-if="loadingFiles" class="loading-text">Checking saved files...</div>
          <div v-else-if="availableFiles.length > 0">
            <h4 class="pick-section-title">Resume from saved:</h4>
            <div
              v-for="f in availableFiles"
              :key="f.name"
              class="pick-item"
              @click="loadFile(f)"
            >
              <span class="pick-icon">{{ f.type === 'yaml' ? '📐' : '📝' }}</span>
              <div class="pick-info">
                <span class="pick-name">{{ f.name }}</span>
                <span class="pick-time">{{ formatTime(f.mtime) }}</span>
              </div>
              <span class="pick-type">{{ f.type === 'yaml' ? 'Outline' : 'Draft' }}</span>
            </div>
          </div>
          <button class="btn btn-primary start-fresh-btn" @click="startFresh">
            ✨ Start Fresh
          </button>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="$emit('close')">Cancel</button>
        </div>
      </template>

      <!-- Step 1: YAML Outline -->
      <template v-if="step === 'yaml'">
        <div class="modal-header">
          <h3>📐 Step 1: Edit YAML Outline</h3>
          <p class="modal-subtitle">Modify the outline structure, then click "Generate Markdown Draft".</p>
        </div>
        <div v-if="yamlLoading" class="loading-text">Generating YAML outline...</div>
        <div v-else class="modal-body">
          <textarea ref="yamlTextarea" class="code-editor" v-model="yamlContent" spellcheck="false"></textarea>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="backToPick">Back</button>
          <button class="btn btn-primary" :disabled="generatingDraft" @click="generateDraft">
            {{ generatingDraft ? 'Generating...' : '📝 Generate Markdown Draft' }}
          </button>
        </div>
      </template>

      <!-- Step 2: Markdown Draft -->
      <template v-if="step === 'markdown'">
        <div class="modal-header">
          <h3>📝 Step 2: Review &amp; Edit Markdown Draft</h3>
          <p class="modal-subtitle" v-if="!draftDone">Generating sections from YAML outline...</p>
          <p class="modal-subtitle" v-else>You can edit the markdown below, then click "Finalize" to generate docx/pdf.</p>
        </div>
        <div class="modal-body">
          <div v-if="sectionStatus" class="section-status">{{ sectionStatus }}</div>
          <textarea
            v-if="draftDone"
            ref="mdTextarea"
            class="code-editor"
            v-model="markdownContent"
            spellcheck="false"
          ></textarea>
          <div v-else class="markdown-preview">
            <div v-for="(part, i) in completedSections" :key="i" class="section-block">
              <div class="section-heading">{{ part.heading }}</div>
              <div class="section-content" v-html="renderMd(part.content)"></div>
            </div>
            <div v-if="currentSectionContent" class="section-block streaming">
              <div class="section-heading">{{ currentSectionHeading }}</div>
              <div class="section-content streaming-content" v-html="renderMd(currentSectionContent)"></div>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="draftDone ? (step = 'yaml') : $emit('close')">
            {{ draftDone ? 'Back' : 'Cancel' }}
          </button>
          <button
            v-if="draftDone"
            class="btn btn-primary"
            :disabled="finalizing"
            @click="finalizeDoc"
          >
            {{ finalizing ? 'Finalizing...' : '✅ Finalize to docx/pdf' }}
          </button>
        </div>
      </template>

      <!-- Step 3: Finalize done -->
      <template v-if="step === 'done'">
        <div class="modal-header">
          <h3>✅ Document Generated</h3>
        </div>
        <div class="modal-body done-body">
          <p class="done-title">{{ finalTitle }}</p>
          <div class="download-links">
            <a v-if="finalDownloadMd" :href="finalDownloadMd + '?download=1'" class="download-btn md" target="_blank">📄 Download .md</a>
            <a v-if="finalDownloadDocx" :href="finalDownloadDocx + '?download=1'" class="download-btn docx" target="_blank">📄 Download .docx</a>
            <a v-if="finalDownloadPdf" :href="finalDownloadPdf + '?download=1'" class="download-btn pdf" target="_blank">📄 Download .pdf</a>
          </div>
        </div>
        <div class="modal-body done-body">
          <p class="done-note">Saved intermediate files have been cleaned up.</p>
        </div>
        <div class="modal-footer">
          <button class="btn btn-primary" @click="onClose">Close</button>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { marked } from 'marked'

const props = defineProps({
  serverUrl: { type: String, default: '' },
  conversationHistory: { type: Array, default: () => [] },
  sessionId: { type: String, default: '' },
})

const emit = defineEmits(['close', 'files-updated'])

// ---------- state ----------
const step = ref('pick')
const availableFiles = ref([])
const loadingFiles = ref(true)

const yamlLoading = ref(false)
const yamlContent = ref('')
const yamlTextarea = ref(null)

const generatingDraft = ref(false)
const draftDone = ref(false)
const markdownContent = ref('')
const mdTextarea = ref(null)

const sectionStatus = ref('')
const completedSections = ref([])
const currentSectionHeading = ref('')
const currentSectionContent = ref('')

const finalizing = ref(false)
const finalTitle = ref('')
const finalDownloadMd = ref('')
const finalDownloadDocx = ref('')
const finalDownloadPdf = ref('')

const apiBase = ''

// ---------- helpers ----------
function renderMd(text) {
  if (!text) return ''
  return marked.parse(text)
}

function formatTime(ts) {
  const d = new Date(ts * 1000)
  return d.toLocaleString()
}

// ---------- file listing ----------
async function fetchAvailableFiles() {
  loadingFiles.value = true
  try {
    const res = await fetch(`${apiBase}/api/doc-workspace/files/`)
    if (res.ok) {
      const data = await res.json()
      availableFiles.value = data.files || []
    }
  } catch {}
  loadingFiles.value = false
}

async function loadFile(file) {
  try {
    const res = await fetch(`${apiBase}/api/doc-workspace/file/${file.name}`)
    if (!res.ok) return
    const data = await res.json()
    if (file.type === 'yaml') {
      yamlContent.value = data.content
      yamlLoading.value = false
      step.value = 'yaml'
      await nextTick()
      if (yamlTextarea.value) {
        yamlTextarea.value.focus()
        yamlTextarea.value.select()
      }
    } else {
      markdownContent.value = data.content
      draftDone.value = true
      step.value = 'markdown'
      await nextTick()
      if (mdTextarea.value) {
        mdTextarea.value.focus()
      }
    }
  } catch {}
}

function startFresh() {
  step.value = 'yaml'
  yamlLoading.value = true
  generateYamlOutline()
}

function backToPick() {
  step.value = 'pick'
  fetchAvailableFiles()
}

function onClose() {
  cleanupUsedFiles()
  emit('close')
}

function onOverlayClick() {
  if (step.value === 'done') onClose()
}

// ---------- YAML outline generation ----------
async function generateYamlOutline() {
  try {
    const payload = {
      conversation_history: props.conversationHistory,
      session_id: props.sessionId,
    }
    let rawYaml = ''
    const gen = createSSEStream(
      `${apiBase}/api/generate-document/generate-yaml-outline/`,
      payload
    )
    for await (const event of gen) {
      if (event.phase === 'yaml_outline') {
        if (event.type === 'chunk') {
          rawYaml += event.content || ''
        } else if (event.type === 'done') {
          yamlContent.value = event.content || rawYaml
        }
      }
    }
    yamlLoading.value = false
    await nextTick()
    if (yamlTextarea.value) {
      yamlTextarea.value.focus()
      yamlTextarea.value.select()
    }
  } catch (e) {
    yamlContent.value = `# Error generating YAML outline:\n# ${e.message}`
    yamlLoading.value = false
  }
}

// ---------- markdown generation ----------
async function generateDraft() {
  generatingDraft.value = true
  step.value = 'markdown'

  try {
    const payload = {
      conversation_history: props.conversationHistory,
      yaml_outline: yamlContent.value,
      session_id: props.sessionId,
    }
    const gen = createSSEStream(
      `${apiBase}/api/generate-document/stream/from-yaml/`,
      payload
    )
    for await (const event of gen) {
      if (event.phase === 'document_from_yaml') {
        if (event.type === 'msg') {
          sectionStatus.value = event.content || ''
        } else if (event.type === 'section_msg') {
          sectionStatus.value = event.content || ''
          currentSectionHeading.value = event.heading || ''
          currentSectionContent.value = ''
        } else if (event.type === 'chunk') {
          currentSectionContent.value += event.content || ''
        } else if (event.type === 'section_done') {
          completedSections.value.push({
            heading: event.heading || '',
            content: event.content || '',
          })
          currentSectionContent.value = ''
          currentSectionHeading.value = ''
        } else if (event.type === 'done') {
          const full = event.content || ''
          markdownContent.value = full
          draftDone.value = true
          sectionStatus.value = ''
          await nextTick()
          if (mdTextarea.value) {
            mdTextarea.value.focus()
          }
        } else if (event.type === 'error') {
          sectionStatus.value = `Error: ${event.content || 'Unknown error'}`
        }
      }
    }
  } catch (e) {
    sectionStatus.value = `Error: ${e.message}`
  } finally {
    generatingDraft.value = false
  }
}

// ---------- finalize ----------
async function finalizeDoc() {
  finalizing.value = true
  try {
    const payload = {
      markdown_content: markdownContent.value,
      session_id: props.sessionId,
    }
    const gen = createSSEStream(
      `${apiBase}/api/generate-document/finalize/`,
      payload
    )
    for await (const event of gen) {
      if (event.phase === 'finalize' && event.type === 'done') {
        step.value = 'done'
        finalTitle.value = event.title || 'Document'
        finalDownloadMd.value = event.download_url_md || ''
        finalDownloadDocx.value = event.download_url_docx || ''
        finalDownloadPdf.value = event.download_url_pdf || ''
        emit('files-updated')
      }
    }
  } catch (e) {
    sectionStatus.value = `Finalize error: ${e.message}`
  } finally {
    finalizing.value = false
  }
}

async function cleanupUsedFiles() {
  for (const f of availableFiles.value) {
    try {
      await fetch(`${apiBase}/api/doc-workspace/files/${f.name}`, { method: 'DELETE' })
    } catch {}
  }
}

// ---------- SSE helper ----------
async function* createSSEStream(url, payload) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    yield { type: 'error', content: `HTTP ${response.status}` }
    return
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n\n')
    buffer = parts.pop()
    for (const part of parts) {
      for (const line of part.split('\n')) {
        if (line.startsWith('data: ')) {
          try {
            yield JSON.parse(line.slice(6))
          } catch {}
        }
      }
    }
  }
}

onMounted(fetchAvailableFiles)
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.modal-container {
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
  width: 90vw;
  height: 85vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
}
.modal-header {
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}
.modal-header h3 {
  margin: 0 0 4px;
  font-size: 16px;
  color: var(--text-primary);
}
.modal-subtitle {
  margin: 0;
  font-size: 12px;
  color: var(--text-muted);
}
.modal-body {
  flex: 1;
  padding: 12px 20px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.code-editor {
  flex: 1;
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  padding: 12px;
  font-family: 'Consolas', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.5;
  resize: none;
  outline: none;
  tab-size: 2;
}
.code-editor:focus {
  border-color: var(--accent-blue);
}
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 20px;
  border-top: 1px solid var(--border-color);
  flex-shrink: 0;
}
.btn {
  padding: 8px 16px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  border: 1px solid var(--border-color);
  cursor: pointer;
  transition: all 0.2s;
}
.btn-secondary {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}
.btn-secondary:hover {
  background: var(--bg-hover);
}
.btn-primary {
  background: var(--accent-blue);
  color: #fff;
  border-color: var(--accent-blue);
}
.btn-primary:hover:not(:disabled) {
  opacity: 0.9;
}
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.loading-text {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  color: var(--text-muted);
}
.empty-text {
  font-size: 14px;
  color: var(--text-muted);
  text-align: center;
  padding: 24px;
}
.section-status {
  font-size: 13px;
  color: var(--text-muted);
  padding: 6px 0;
  flex-shrink: 0;
}
.markdown-preview {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
}
.section-block {
  margin-bottom: 16px;
}
.section-heading {
  font-size: 15px;
  font-weight: 700;
  color: var(--accent-blue);
  margin-bottom: 6px;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--border-color);
}
.section-content {
  font-size: 13px;
  color: var(--text-primary);
  line-height: 1.6;
}
.streaming {
  opacity: 0.8;
}
.streaming-content::after {
  content: '▌';
  animation: blink 0.8s infinite;
}
@keyframes blink {
  50% { opacity: 0; }
}
.done-body {
  align-items: center;
  justify-content: center;
  text-align: center;
  gap: 16px;
}
.done-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
}
.done-note {
  font-size: 12px;
  color: var(--text-muted);
}
.download-links {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: center;
}
.download-btn {
  display: inline-block;
  padding: 10px 20px;
  border-radius: var(--radius-sm);
  font-size: 14px;
  font-weight: 600;
  text-decoration: none;
  transition: all 0.2s;
}
.download-btn.md {
  background: #4a90d9;
  color: #fff;
}
.download-btn.docx {
  background: #2b579a;
  color: #fff;
}
.download-btn.pdf {
  background: #d34f4f;
  color: #fff;
}
.download-btn:hover {
  opacity: 0.85;
}

/* Pick/resume panel */
.pick-body {
  flex-direction: column;
  gap: 12px;
  padding: 20px;
  overflow-y: auto;
}
.pick-section-title {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0 0 8px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.pick-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all 0.2s;
  margin-bottom: 6px;
}
.pick-item:hover {
  background: var(--bg-hover);
  border-color: var(--accent-blue);
}
.pick-icon {
  font-size: 20px;
  flex-shrink: 0;
}
.pick-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.pick-name {
  font-family: 'Consolas', monospace;
  font-size: 13px;
  color: var(--text-primary);
  word-break: break-all;
}
.pick-time {
  font-size: 11px;
  color: var(--text-muted);
}
.pick-type {
  font-size: 11px;
  color: var(--accent-cyan);
  background: var(--bg-secondary);
  padding: 2px 8px;
  border-radius: 10px;
  flex-shrink: 0;
}
.start-fresh-btn {
  align-self: center;
  margin-top: 12px;
  padding: 10px 24px;
  font-size: 14px;
}
</style>