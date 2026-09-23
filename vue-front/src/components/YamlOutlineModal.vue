<template>
  <div class="modal-overlay" @click.self="onOverlayClick">
    <div class="modal-container">
      <!-- Recovery: pick existing file -->
      <template v-if="step === 'pick'">
        <div class="modal-header">
          <h3>Document Generation</h3>
          <p class="modal-subtitle">Resume from a saved draft or start fresh.</p>
          <button class="close-btn" @click="onClose" title="Close">✕</button>
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
            >
              <div class="pick-item-body">
                <span class="pick-icon">Outline</span>
                <div class="pick-info">
                  <span class="pick-name">{{ f.name }}</span>
                  <span class="pick-time">{{ formatTime(f.mtime) }}</span>
                </div>
              </div>
              <div class="pick-actions">
                <button class="pick-chat" @click.stop="sendYamlToChat(f)" title="Ask AI to gather info">Ask AI</button>
                <button class="pick-continue" @click.stop="loadFile(f)" title="Continue">Continue</button>
                <button class="pick-edit" @click.stop="confirmEditOutline(f)" title="Edit YAML">Edit</button>
                <button class="pick-view" @click.stop="viewYaml(f)" title="View YAML">View</button>
                <button class="pick-delete" @click.stop="confirmDelete(f)" title="Delete">✕</button>
              </div>
            </div>
          </div>
          <button class="btn btn-primary start-fresh-btn" @click="startFresh">Start Fresh</button>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="$emit('close')">Cancel</button>
        </div>
      </template>

      <!-- Step 1: YAML Outline -->
      <template v-if="step === 'yaml'">
        <div class="modal-header">
          <h3>Step 1: Edit YAML Outline</h3>
          <p class="modal-subtitle">{{ sectionCount }} sections will be generated. Modify then click next.</p>
          <button class="close-btn" @click="onClose" title="Close">✕</button>
        </div>
        <div class="modal-body">
          <div v-if="yamlLoading" class="loading-overlay">Generating YAML outline...</div>
          <div class="user-prompt-area" v-if="!yamlContent && !yamlLoading">
            <label class="user-prompt-label">Optional instructions for AI outline generation:</label>
            <textarea
              class="user-prompt-input"
              v-model="userPrompt"
              placeholder="e.g. Focus on price trends, include a comparison table, emphasize 2023-2024 data..."
              rows="2"
              spellcheck="false"
            ></textarea>
            <button class="btn btn-primary" :disabled="generatingYaml" @click="generateYamlOutline">
              {{ generatingYaml ? 'Generating...' : 'Generate with AI' }}
            </button>
          </div>
          <template v-if="yamlContent">
            <details class="yaml-format-hint">
              <summary>YAML format reference</summary>
              <pre class="yaml-format-pre">title: "Document Title"
sections:
  - heading: "1. Section"
    description: "Brief description"
    elements:                    # optional: text/table/image
      - type: text
        description: "Describe the text to write"
      - type: table
        description: "Describe the table"
      - type: image
        description: "Describe the chart/image"
    subsections:
      - heading: "1.1 Subsection"
        description: "Brief description"
        elements:
          - type: text
            description: "..."
</pre>
            </details>
            <div class="editor-mode-bar">
              <button
                :class="['mode-tab', { active: editorMode === 'code' }]"
                @click="switchToCode"
              >Code</button>
              <button
                :class="['mode-tab', { active: editorMode === 'visual' }]"
                @click="switchToVisual"
              >Visual</button>
            </div>
            <div v-if="parseError" class="parse-error">{{ parseError }}</div>
            <textarea
              v-show="editorMode === 'code'"
              ref="yamlTextarea"
              class="code-editor"
              v-model="yamlContent"
              spellcheck="false"
            ></textarea>
            <YamlVisualEditor
              v-show="editorMode === 'visual'"
              v-model="yamlContent"
            />
          </template>
        </div>
        <div class="modal-footer" v-if="!yamlLoading && yamlContent">
          <button class="btn btn-secondary" style="margin-right:auto" @click="backToPick">Back</button>
          <button class="btn btn-secondary" @click="saveYaml" :disabled="!yamlBase">Save</button>
          <button class="btn btn-primary" :disabled="generatingDraft" @click="startGeneratingSections">
            {{ generatingDraft ? 'Starting...' : 'Generate Sections' }}
          </button>
        </div>
      </template>

      <!-- Step 2: Generate sections one by one, confirmed by user -->
      <template v-if="step === 'sections'">
        <div class="modal-header">
          <h3>Step 2: Section {{ currentSectionIndex + 1 }} / {{ totalSections }}</h3>
          <p class="modal-subtitle">{{ currentSectionHeading || 'Generating...' }}</p>
          <button class="close-btn" @click="onClose" title="Close">✕</button>
        </div>
        <div class="modal-body">
          <!-- Streaming preview for current section -->
          <div v-if="!currentSectionDone" class="markdown-preview">
            <div v-for="(part, i) in confirmedSections" :key="i" class="section-block confirmed">
              <div class="section-heading">{{ part.heading }}</div>
              <div class="section-content" v-html="renderMd(part.content)"></div>
            </div>
            <div class="section-block streaming">
              <div class="section-heading">{{ currentSectionHeading }}</div>
              <div class="section-content streaming-content" v-html="renderMd(currentSectionContent)"></div>
            </div>
          </div>
          <!-- Editable textarea for current section -->
          <div v-else class="section-edit-area">
            <div class="confirmed-indicator">
              <span v-for="(part, i) in confirmedSections" :key="i" class="confirmed-badge" @click="editSection(i)">Section {{ i + 1 }}</span>
              <span class="current-badge">Section {{ currentSectionIndex + 1 }}</span>
            </div>
            <div class="confirmed-preview">
              <div
                v-for="(part, i) in confirmedSections"
                :key="'confirmed-' + i"
                class="section-block confirmed"
                @click="editSection(i)"
              >
                <div class="section-heading">{{ part.heading }}</div>
                <div class="section-content truncated" v-html="renderMd(truncate(part.content, 300))"></div>
              </div>
            </div>
            <label class="section-edit-label">{{ currentSectionHeading }}</label>
            <textarea
              ref="sectionTextarea"
              class="code-editor"
              v-model="currentSectionEdit"
              spellcheck="false"

            ></textarea>
            <details class="preview-toggle">
              <summary>Preview (images, tables)</summary>
              <div class="edit-preview" v-html="renderMd(currentSectionEdit)"></div>
            </details>
          </div>
        </div>
        <div class="modal-footer">
          <button
            v-if="currentSectionDone"
            class="btn btn-primary"
            @click="confirmSection"
          >
            {{ currentSectionIndex + 1 < totalSections ? 'Confirm & Next' : 'Confirm & Finish' }}
          </button>
        </div>
      </template>

      <!-- Step 3: Review & Finalize -->
      <template v-if="step === 'review'">
        <div class="modal-header">
          <h3>Step 3: Review Full Document & Finalize</h3>
          <p class="modal-subtitle">All {{ confirmedSections.length }} sections confirmed. You can still edit any section below.</p>
          <button class="close-btn" @click="onClose" title="Close">✕</button>
        </div>
        <div class="modal-body">
          <div class="confirmed-indicator">
            <span v-for="(_, i) in confirmedSections" :key="i" class="confirmed-badge" @click="editSection(i)">Section {{ i + 1 }}</span>
          </div>
          <textarea
            ref="finalTextarea"
            class="code-editor"
            v-model="mergedContent"
            spellcheck="false"
          ></textarea>
          <details class="preview-toggle">
            <summary>Preview (images, tables)</summary>
            <div class="edit-preview" v-html="renderMd(mergedContent)"></div>
          </details>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" style="margin-right:auto" @click="backToSectionEdit">Back</button>
          <button class="btn btn-secondary" @click="saveDraft" :disabled="!yamlBase">Save Draft</button>
          <button class="btn btn-primary" :disabled="finalizing" @click="finalizeDoc">
            {{ finalizing ? 'Finalizing...' : 'Finalize to docx/pdf' }}
          </button>
        </div>
      </template>

      <!-- Done -->
      <template v-if="step === 'done'">
        <div class="modal-header">
          <h3>Document Generated</h3>
          <button class="close-btn" @click="onClose" title="Close">✕</button>
        </div>
        <div class="modal-body done-body">
          <p class="done-title">{{ finalTitle }}</p>
          <div class="download-links">
            <a v-if="finalDownloadMd" :href="finalDownloadMd + '?download=1'" class="download-btn md" target="_blank">Download .md</a>
            <a v-if="finalDownloadDocx" :href="finalDownloadDocx + '?download=1'" class="download-btn docx" target="_blank">Download .docx</a>
            <a v-if="finalDownloadPdf" :href="finalDownloadPdf + '?download=1'" class="download-btn pdf" target="_blank">Download .pdf</a>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-primary" @click="onClose">Close</button>
        </div>
      </template>
    <!-- YAML viewer -->
      <div v-if="viewYamlFile" class="yaml-overlay" @click.self="viewYamlFile = null">
        <div class="confirm-dialog yaml-viewer">
          <div class="yaml-viewer-header">
            <span>{{ viewYamlFile.name }}</span>
            <button class="close-btn" @click="viewYamlFile = null" title="Close">✕</button>
          </div>
          <textarea class="code-editor yaml-viewer-body" readonly :value="yamlViewContent" spellcheck="false"></textarea>
        </div>
      </div>
    <!-- Confirm dialog -->
      <div v-if="confirmFile" class="confirm-overlay" @click.self="confirmFile = null">
        <div class="confirm-dialog">
          <p>Delete "{{ confirmFile.name }}"? This will also remove any associated drafts.</p>
          <div class="confirm-actions">
            <button class="btn btn-secondary" @click="confirmFile = null">Cancel</button>
            <button class="btn btn-danger" @click="doDelete">Delete</button>
          </div>
        </div>
      </div>
    <!-- Edit YAML confirm dialog -->
      <div v-if="editYamlFile" class="confirm-overlay" @click.self="editYamlFile = null">
        <div class="confirm-dialog">
          <p>Edit "{{ editYamlFile.name }}"? This will discard any generated drafts and return to the YAML editing step.</p>
          <div class="confirm-actions">
            <button class="btn btn-secondary" @click="editYamlFile = null">Cancel</button>
            <button class="btn btn-primary" @click="doEditYaml">Edit</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { marked } from 'marked'
import * as jsyaml from 'js-yaml'
import YamlVisualEditor from './YamlVisualEditor.vue'

const props = defineProps({
  serverUrl: { type: String, default: '' },
  conversationHistory: { type: Array, default: () => [] },
  sessionId: { type: String, default: '' },
})
const emit = defineEmits(['close', 'files-updated', 'running', 'send-yaml'])

const step = ref('pick')
const availableFiles = ref([])
const loadingFiles = ref(true)

const yamlLoading = ref(false)
const yamlContent = ref('')
const yamlBase = ref('')
const yamlTextarea = ref(null)
const generatingDraft = ref(false)
const userPrompt = ref('')
const generatingYaml = ref(false)
const editorMode = ref('code')
const parseError = ref('')

const totalSections = ref(0)
const currentSectionIndex = ref(0)
const currentSectionHeading = ref('')
const currentSectionContent = ref('')
const currentSectionEdit = ref('')
const currentSectionDone = ref(false)
const sectionTextarea = ref(null)

const confirmedSections = ref([])

const finalizing = ref(false)
const finalTitle = ref('')
const finalDownloadMd = ref('')
const finalDownloadDocx = ref('')
const finalDownloadPdf = ref('')
const finalTextarea = ref(null)
const confirmFile = ref(null)
const editYamlFile = ref(null)
const viewYamlFile = ref(null)
const yamlViewContent = ref('')

const docTitle = computed(() => {
  const m = yamlContent.value.match(/^title:\s*["'](.+?)["']/m)
  return m ? m[1] : ''
})

const isBusy = computed(() => yamlLoading.value || generatingDraft.value || finalizing.value || generatingYaml.value)
watch(isBusy, (v) => emit('running', v))

const sectionCount = computed(() => {
  const m = yamlContent.value.match(/^  - heading:/gm)
  return m ? m.length : 0
})

const mergedContent = computed({
  get: () => {
    const titleLine = docTitle.value ? `# ${docTitle.value}\n\n` : ''
    const parts = confirmedSections.value.map((s, i) =>
      `## ${s.heading}\n\n${s.content}`
    ).join('\n\n')
    return titleLine + parts
  },
  set: (val) => {
    // Reset tracking when user edits the merged text directly
    // Keeps merged content as-is for finalize
  }
})

function renderMd(text) {
  if (!text) return ''
  return marked.parse(text)
}

function truncate(text, maxLen) {
  if (!text || text.length <= maxLen) return text || ''
  return text.slice(0, maxLen) + '...'
}

function formatTime(ts) {
  return new Date(ts * 1000).toLocaleString()
}

async function fetchAvailableFiles() {
  loadingFiles.value = true
  try {
    const res = await fetch('/api/doc-workspace/files/')
    if (res.ok) {
      const data = await res.json()
      const sid = props.sessionId
      availableFiles.value = (data.files || []).filter(f => f.name.startsWith(`outline_${sid}_`))
    }
  } catch {}
  loadingFiles.value = false
}

function parseSectionsFromMd(text) {
  const lines = text.split('\n')
  const sections = []
  let current = null
  for (const line of lines) {
    const m = line.match(/^##\s+(.+)$/)
    if (m) {
      if (current) sections.push(current)
      current = { heading: m[1].trim(), content: '' }
    } else if (current) {
      current.content += line + '\n'
    }
  }
  if (current) sections.push(current)
  return sections
}

async function loadFile(file) {
  try {
    const res = await fetch(`/api/doc-workspace/file/${file.name}`)
    if (!res.ok) return
    const data = await res.json()
    yamlContent.value = data.content

    const base = file.name.replace(/^outline_/, '').replace(/\.yaml$/, '')
    yamlBase.value = base

    // 1. Try merged draft
    try {
      const draftRes = await fetch(`/api/doc-workspace/file/draft_${base}.md`)
      if (draftRes.ok) {
        const draftData = await draftRes.json()
        const sections = parseSectionsFromMd(draftData.content)
        if (sections.length > 0) {
          confirmedSections.value = sections
          step.value = 'review'
          await nextTick()
          if (finalTextarea.value) finalTextarea.value.focus()
          return
        }
      }
    } catch {}

    // 2. Try individual section files
    const sectionFiles = []
    for (let i = 0; i < 100; i++) {
      const name = `draft_${base}_s${String(i).padStart(2, '0')}.md`
      try {
        const secRes = await fetch(`/api/doc-workspace/file/${name}`)
        if (secRes.ok) {
          const secData = await secRes.json()
          const content = secData.content || ''
          const headingMatch = content.match(/^##\s+(.+)$/m)
          const heading = headingMatch ? headingMatch[1].trim() : `Section ${i + 1}`
          const body = content.replace(/^##\s+.+(\n|$)/, '').trim()
          sectionFiles.push({ heading, content: body, index: i })
        } else {
          break
        }
      } catch { break }
    }
    if (sectionFiles.length > 0) {
      const last = sectionFiles.pop()
      confirmedSections.value = sectionFiles
      currentSectionIndex.value = sectionFiles.length
      totalSections.value = sectionFiles.length + 1
      currentSectionDone.value = true
      currentSectionHeading.value = last.heading
      currentSectionEdit.value = last.content
      step.value = 'sections'
      await nextTick()
      if (sectionTextarea.value) sectionTextarea.value.focus()
      return
    }

    // 3. Nothing found — start from YAML
    step.value = 'yaml'
    await nextTick()
    if (yamlTextarea.value) yamlTextarea.value.focus()
  } catch {}
}

function startFresh() {
  step.value = 'yaml'
  yamlContent.value = ''
  userPrompt.value = ''
  yamlLoading.value = false
}

function backToPick() {
  step.value = 'pick'
  editorMode.value = 'code'
  fetchAvailableFiles()
}

function switchToCode() {
  editorMode.value = 'code'
  parseError.value = ''
  nextTick(() => {
    if (yamlTextarea.value) yamlTextarea.value.focus()
  })
}

function switchToVisual() {
  parseError.value = ''
  try {
    jsyaml.load(yamlContent.value)
    editorMode.value = 'visual'
  } catch (e) {
    parseError.value = `Cannot switch to Visual mode: YAML parse error — ${e.message}`
  }
}

async function saveFile(filename, content) {
  try {
    await fetch(`/api/doc-workspace/save/${filename}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    })
  } catch {}
}

async function saveYaml() {
  if (!yamlBase.value) return
  await saveFile(`outline_${yamlBase.value}.yaml`, yamlContent.value)
}

async function saveDraft() {
  if (!yamlBase.value) return
  await saveFile(`draft_${yamlBase.value}.md`, mergedContent.value)
}

async function doEditYaml() {
  const file = editYamlFile.value
  if (!file) return
  editYamlFile.value = null
  try {
    const res = await fetch(`/api/doc-workspace/file/${file.name}`)
    if (!res.ok) return
    const data = await res.json()
    const base = file.name.replace(/^outline_/, '').replace(/\.yaml$/, '')
    const idx = base.lastIndexOf('_')
    const sessionId = base.slice(0, idx)
    const yamlId = base.slice(idx + 1)
    await fetch(`/api/doc-workspace/drafts/${sessionId}/${yamlId}`, { method: 'DELETE' })
    yamlContent.value = data.content
    step.value = 'yaml'
    await nextTick()
    if (yamlTextarea.value) yamlTextarea.value.focus()
  } catch {}
}

async function sendYamlToChat(file) {
  try {
    const res = await fetch(`/api/doc-workspace/file/${file.name}`)
    if (!res.ok) return
    const data = await res.json()
    const promptRes = await fetch('/api/generate-document/yaml-to-prompt/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ yaml_content: data.content }),
    })
    if (!promptRes.ok) return
    const promptData = await promptRes.json()
    emit('send-yaml', promptData.prompt)
  } catch {}
}

function confirmEditOutline(file) {
  editYamlFile.value = file
}

async function viewYaml(file) {
  try {
    const res = await fetch(`/api/doc-workspace/file/${file.name}`)
    if (res.ok) {
      const data = await res.json()
      yamlViewContent.value = data.content
      viewYamlFile.value = file
    }
  } catch {}
}



function confirmDelete(file) {
  confirmFile.value = file
}

async function doDelete() {
  const file = confirmFile.value
  if (!file) return
  confirmFile.value = null
  try {
    await fetch(`/api/doc-workspace/outline/${file.name}`, { method: 'DELETE' })
    availableFiles.value = availableFiles.value.filter(f => f.name !== file.name)
  } catch {}
}

function onClose() {
  emit('running', false)
  cleanupUsedFiles()
  emit('close')
}

function onOverlayClick() {
  onClose()
}

// YAML outline generation
async function generateYamlOutline() {
  generatingYaml.value = true
  yamlLoading.value = true
  try {
    const payload = {
      conversation_history: props.conversationHistory,
      session_id: props.sessionId,
      user_prompt: userPrompt.value.trim() || undefined,
    }
    let rawYaml = ''
    const gen = createSSEStream('/api/generate-document/generate-yaml-outline/', payload)
    for await (const event of gen) {
      if (event.phase === 'yaml_outline') {
        if (event.type === 'chunk') {
          rawYaml += event.content || ''
          yamlContent.value = rawYaml
        } else if (event.type === 'done') {
          yamlContent.value = event.content || rawYaml
          const base = event.yaml_base || ''
          const sid = props.sessionId
          yamlBase.value = sid ? `${sid}_${base}` : base
        }
      }
    }
    yamlLoading.value = false
    generatingYaml.value = false
    await nextTick()
    if (yamlTextarea.value) yamlTextarea.value.focus()
  } catch (e) {
    yamlContent.value = `# Error generating YAML outline:\n# ${e.message}`
    yamlLoading.value = false
    generatingYaml.value = false
  }
}

// Start generating sections one by one
async function startGeneratingSections() {
  await saveYaml()
  generatingDraft.value = true
  step.value = 'sections'
  confirmedSections.value = []
  currentSectionIndex.value = 0
  totalSections.value = sectionCount.value
  generateNextSection()
}

async function generateNextSection() {
  currentSectionDone.value = false
  currentSectionContent.value = ''
  currentSectionEdit.value = ''

  const payload = {
    conversation_history: props.conversationHistory,
    yaml_outline: yamlContent.value,
    session_id: props.sessionId,
    section_index: currentSectionIndex.value,
    yaml_base: yamlBase.value,
  }

  try {
    const gen = createSSEStream('/api/generate-document/stream/from-yaml/', payload)
    for await (const event of gen) {
      if (event.phase === 'document_from_yaml') {
        if (event.type === 'section_msg') {
          currentSectionHeading.value = event.heading || ''
        } else if (event.type === 'chunk') {
          currentSectionContent.value += event.content || ''
        } else if (event.type === 'section_done') {
          currentSectionContent.value = event.content || ''
          currentSectionEdit.value = event.content || ''
          currentSectionDone.value = true
          totalSections.value = event.total_sections || totalSections.value
          await nextTick()
          if (sectionTextarea.value) sectionTextarea.value.focus()
        } else if (event.type === 'error') {
          currentSectionContent.value = `Error: ${event.content || 'Unknown'}`
          currentSectionDone.value = true
        }
      }
    }
  } catch (e) {
    currentSectionContent.value = `Error: ${e.message}`
    currentSectionDone.value = true
  } finally {
    generatingDraft.value = false
  }
}

// Confirm current section and move to next
async function confirmSection() {
  confirmedSections.value.push({
    heading: currentSectionHeading.value,
    content: currentSectionEdit.value,
  })
  if (currentSectionIndex.value + 1 < totalSections.value) {
    currentSectionIndex.value++
    generateNextSection()
  } else {
    await saveDraft()
    step.value = 'review'
    nextTick(() => {
      if (finalTextarea.value) finalTextarea.value.focus()
    })
  }
}

function editSection(idx) {
  step.value = 'sections'
  currentSectionIndex.value = idx
  const sec = confirmedSections.value[idx]
  currentSectionHeading.value = sec.heading
  currentSectionEdit.value = sec.content
  currentSectionDone.value = true
  confirmedSections.value.splice(idx, 1)
  nextTick(() => {
    if (sectionTextarea.value) sectionTextarea.value.focus()
  })
}

function backToSectionEdit() {
  if (confirmedSections.value.length > 0) {
    editSection(confirmedSections.value.length - 1)
  }
}

// Finalize
async function finalizeDoc() {
  finalizing.value = true
  try {
    const titleLine = docTitle.value ? `# ${docTitle.value}\n\n` : ''
    const fullMd = titleLine + confirmedSections.value.map((s, i) =>
      `## ${s.heading}\n\n${s.content}`
    ).join('\n\n')
    const payload = {
      markdown_content: fullMd,
      session_id: props.sessionId,
      yaml_base: yamlBase.value,
      conversation_history: props.conversationHistory,
    }
    const gen = createSSEStream('/api/generate-document/finalize/', payload)
    for await (const event of gen) {
      if (event.phase === 'finalize' && event.type === 'done') {
        step.value = 'done'
        finalTitle.value = event.title || 'Document'
        finalDownloadMd.value = event.download_url_md || ''
        finalDownloadDocx.value = event.download_url_docx || ''
        finalDownloadPdf.value = event.download_url_pdf || ''
        emit('files-updated', {
          id: Date.now(),
          title: event.title || 'Document',
          downloadUrlMd: event.download_url_md || '',
          downloadUrlDocx: event.download_url_docx || '',
          downloadUrlPdf: event.download_url_pdf || '',
          createdAt: Date.now(),
        })
      }
    }
  } catch (e) {
    console.error('Finalize error:', e)
  } finally {
    finalizing.value = false
  }
}

async function cleanupUsedFiles() {}

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
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-container { background: var(--bg-primary); border: 1px solid var(--border-color); border-radius: var(--radius); width: 90vw; height: 85vh; display: flex; flex-direction: column; box-shadow: 0 8px 32px rgba(0,0,0,0.3); }
.modal-header { padding: 16px 20px; border-bottom: 1px solid var(--border-color); flex-shrink: 0; position: relative; }
.modal-header h3 { margin: 0 0 4px; font-size: 16px; color: var(--text-primary); }
.modal-subtitle { margin: 0; font-size: 12px; color: var(--text-muted); }
.close-btn { position: absolute; top: 12px; right: 16px; background: none; border: none; color: var(--text-muted); font-size: 18px; cursor: pointer; padding: 4px 8px; line-height: 1; border-radius: var(--radius-sm); }
.close-btn:hover { background: var(--bg-hover); color: var(--text-primary); }
.modal-body { flex: 1; padding: 12px 20px; overflow-y: auto; display: flex; flex-direction: column; }
.code-editor { flex: 1; background: var(--bg-tertiary); color: var(--text-primary); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 12px; font-family: 'Consolas','Courier New',monospace; font-size: 13px; line-height: 1.5; resize: none; outline: none; tab-size: 2; }
.code-editor:focus { border-color: var(--accent-blue); }
.modal-footer { display: flex; justify-content: flex-end; gap: 8px; padding: 12px 20px; border-top: 1px solid var(--border-color); flex-shrink: 0; }
.btn { padding: 8px 16px; border-radius: var(--radius-sm); font-size: 13px; border: 1px solid var(--border-color); cursor: pointer; transition: all 0.2s; }
.btn-secondary { background: var(--bg-tertiary); color: var(--text-secondary); }
.btn-secondary:hover { background: var(--bg-hover); }
.btn-primary { background: var(--accent-blue); color: #fff; border-color: var(--accent-blue); }
.btn-primary:hover:not(:disabled) { opacity: 0.9; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.loading-text { flex: 1; display: flex; align-items: center; justify-content: center; font-size: 14px; color: var(--text-muted); }
.loading-overlay { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-size: 14px; color: var(--text-muted); z-index: 1; pointer-events: none; }
.empty-text { font-size: 14px; color: var(--text-muted); text-align: center; padding: 24px; }
.markdown-preview { flex: 1; overflow-y: auto; padding: 8px 0; }
.section-block { margin-bottom: 12px; }
.section-block.confirmed { opacity: 0.6; }
.section-heading { font-size: 14px; font-weight: 700; color: var(--accent-blue); margin-bottom: 4px; padding-bottom: 2px; border-bottom: 1px solid var(--border-color); }
.section-content { font-size: 13px; color: var(--text-primary); line-height: 1.6; }
.streaming { opacity: 0.8; }
.streaming-content::after { content: '|'; animation: blink 0.8s infinite; }
@keyframes blink { 50% { opacity: 0; } }
.section-edit-area { flex: 1; display: flex; flex-direction: column; gap: 8px; }
.confirmed-preview { max-height: 30%; overflow-y: auto; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 8px 12px; flex-shrink: 0; }
.confirmed-preview .section-block { margin-bottom: 8px; cursor: pointer; }
.confirmed-preview .section-block:hover { background: var(--bg-hover); }
.confirmed-preview .section-content.truncated { font-size: 12px; opacity: 0.7; }
.section-edit-label { font-size: 14px; font-weight: 700; color: var(--accent-blue); flex-shrink: 0; }
.confirmed-indicator { display: flex; gap: 6px; flex-wrap: wrap; flex-shrink: 0; }
.confirmed-badge { font-size: 11px; color: var(--accent-green); background: var(--bg-tertiary); padding: 3px 8px; border-radius: 10px; cursor: pointer; }
.confirmed-badge:hover { background: var(--bg-hover); }
.current-badge { font-size: 11px; color: var(--accent-cyan); background: var(--bg-tertiary); padding: 3px 8px; border-radius: 10px; }
.done-body { align-items: center; justify-content: center; text-align: center; gap: 16px; }
.done-title { font-size: 18px; font-weight: 700; color: var(--text-primary); }
.download-links { display: flex; gap: 12px; flex-wrap: wrap; justify-content: center; }
.download-btn { display: inline-block; padding: 10px 20px; border-radius: var(--radius-sm); font-size: 14px; font-weight: 600; text-decoration: none; transition: all 0.2s; }
.download-btn.md { background: #4a90d9; color: #fff; }
.download-btn.docx { background: #2b579a; color: #fff; }
.download-btn.pdf { background: #d34f4f; color: #fff; }
.download-btn:hover { opacity: 0.85; }
.pick-body { flex-direction: column; gap: 12px; padding: 20px; overflow-y: auto; }
.pick-section-title { font-size: 13px; color: var(--text-secondary); margin: 0 0 8px; text-transform: uppercase; letter-spacing: 0.5px; }
.pick-item { display: flex; align-items: center; gap: 12px; padding: 10px 14px; background: var(--bg-tertiary); border: 1px solid var(--border-color); border-radius: var(--radius-sm); cursor: pointer; transition: all 0.2s; margin-bottom: 6px; }
.pick-item:hover { background: var(--bg-hover); border-color: var(--accent-blue); }
.pick-icon { font-size: 11px; color: var(--accent-cyan); background: var(--bg-secondary); padding: 2px 8px; border-radius: 10px; flex-shrink: 0; }
.pick-info { flex: 1; display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.pick-name { font-family: 'Consolas',monospace; font-size: 13px; color: var(--text-primary); word-break: break-all; }
.pick-time { font-size: 11px; color: var(--text-muted); }
.pick-actions { margin-left: auto; display: flex; gap: 4px; flex-shrink: 0; }
.pick-chat { background: var(--bg-tertiary); border: 1px solid var(--border-color); color: var(--text-secondary); font-size: 13px; cursor: pointer; padding: 4px 10px; border-radius: var(--radius-sm); line-height: 1; }
.pick-chat:hover { background: var(--bg-hover); color: var(--text-primary); border-color: var(--accent-blue); }
.pick-continue { background: var(--accent-blue); border: 1px solid var(--accent-blue); color: #fff; font-size: 13px; cursor: pointer; padding: 4px 12px; border-radius: var(--radius-sm); line-height: 1; font-weight: 600; }
.pick-continue:hover { opacity: 0.9; }
.pick-edit { background: var(--bg-tertiary); border: 1px solid var(--border-color); color: var(--accent-blue); font-size: 13px; cursor: pointer; padding: 4px 10px; border-radius: var(--radius-sm); line-height: 1; }
.pick-edit:hover { background: var(--accent-blue); color: #fff; }
.pick-view { background: var(--bg-tertiary); border: 1px solid var(--border-color); color: var(--text-secondary); font-size: 13px; cursor: pointer; padding: 4px 10px; border-radius: var(--radius-sm); line-height: 1; }
.pick-view:hover { background: var(--bg-hover); color: var(--text-primary); border-color: var(--accent-blue); }
.pick-delete { background: none; border: none; color: #d34f4f; font-size: 18px; cursor: pointer; padding: 4px 10px; border-radius: var(--radius-sm); line-height: 1; }
.pick-delete:hover { background: rgba(211,79,79,0.1); }
.yaml-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1100; }
.yaml-viewer { width: 95vw; max-width: 1400px; height: 90vh; display: flex; flex-direction: column; }
.yaml-viewer .code-editor { width: 100%; }
.yaml-viewer-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; font-size: 14px; font-weight: 700; color: var(--text-primary); }
.yaml-viewer-header .close-btn { position: static; font-size: 20px; padding: 2px 8px; }
.yaml-viewer-actions { display: flex; align-items: center; gap: 8px; }
.btn-sm { padding: 4px 12px; font-size: 12px; }
.yaml-viewer-body { min-height: 300px; }
.start-fresh-btn { align-self: center; margin-top: 12px; padding: 10px 24px; font-size: 14px; }
.confirm-overlay { position: absolute; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 10; border-radius: var(--radius); }
.confirm-dialog { background: var(--bg-primary); border: 1px solid var(--border-color); border-radius: var(--radius); padding: 24px; box-shadow: 0 4px 16px rgba(0,0,0,0.3); }
.confirm-dialog:not(.yaml-viewer) { max-width: 400px; }
.confirm-dialog p { margin: 0 0 16px; font-size: 14px; color: var(--text-primary); line-height: 1.5; word-break: break-all; }
.confirm-actions { display: flex; justify-content: flex-end; gap: 8px; }
.btn-danger { background: #d34f4f; color: #fff; border-color: #d34f4f; }
.btn-danger:hover { opacity: 0.9; }
.preview-toggle { flex-shrink: 0; margin-top: 6px; }
.preview-toggle summary { font-size: 12px; color: var(--accent-blue); cursor: pointer; user-select: none; padding: 4px 8px; border-radius: var(--radius-sm); background: var(--bg-tertiary); display: inline-block; }
.preview-toggle summary:hover { background: var(--bg-hover); }
.edit-preview { background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 12px 16px; margin-top: 6px; max-height: 400px; overflow-y: auto; font-size: 13px; line-height: 1.6; }
.edit-preview img { max-width: 100%; height: auto; border-radius: var(--radius-sm); margin: 8px 0; }
.edit-preview table { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 13px; }
.edit-preview th, .edit-preview td { border: 1px solid var(--border-color); padding: 6px 10px; text-align: left; }
.edit-preview th { background: var(--bg-tertiary); font-weight: 600; }
.user-prompt-area { flex: 1; display: flex; flex-direction: column; justify-content: center; align-items: center; gap: 12px; padding: 24px; }
.user-prompt-label { font-size: 14px; color: var(--text-secondary); font-weight: 600; }
.user-prompt-input { width: 100%; max-width: 560px; background: var(--bg-tertiary); color: var(--text-primary); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 10px 14px; font-family: inherit; font-size: 14px; line-height: 1.5; resize: vertical; outline: none; }
.user-prompt-input:focus { border-color: var(--accent-blue); }
.editor-mode-bar { display: flex; gap: 0; flex-shrink: 0; margin-bottom: 8px; border: 1px solid var(--border-color); border-radius: var(--radius-sm); overflow: hidden; align-self: flex-start; }
.mode-tab { background: var(--bg-tertiary); color: var(--text-secondary); border: none; padding: 6px 16px; font-size: 13px; cursor: pointer; transition: all 0.2s; }
.mode-tab:not(:last-child) { border-right: 1px solid var(--border-color); }
.mode-tab:hover { background: var(--bg-hover); color: var(--text-primary); }
.mode-tab.active { background: var(--accent-blue); color: #fff; }
.parse-error { flex-shrink: 0; padding: 8px 12px; background: rgba(217,83,79,0.1); border: 1px solid var(--accent-red); border-radius: var(--radius-sm); font-size: 12px; color: var(--accent-red); margin-bottom: 8px; }
.yaml-format-hint { flex-shrink: 0; margin-bottom: 8px; font-size: 12px; color: var(--text-muted); }
.yaml-format-hint summary { cursor: pointer; user-select: none; padding: 4px 8px; border-radius: var(--radius-sm); background: var(--bg-tertiary); display: inline-block; }
.yaml-format-hint summary:hover { background: var(--bg-hover); }
.yaml-format-pre { background: var(--bg-tertiary); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 10px 14px; font-family: 'Consolas','Courier New',monospace; font-size: 12px; line-height: 1.4; overflow-x: auto; margin: 6px 0 0; white-space: pre; color: var(--text-secondary); }
</style>