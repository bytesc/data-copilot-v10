<template>
  <div class="visual-editor">
    <div class="ve-field">
      <label class="ve-label">Title</label>
      <input class="ve-input" v-model="draft.title" placeholder="Document Title" @input="emitDraft" />
    </div>

    <div class="ve-section-group">
      <div class="ve-group-header">
        <label class="ve-label">Sections</label>
        <button class="ve-btn ve-btn-add" @click="addSection">+ Add Section</button>
      </div>

      <div v-for="(sec, si) in draft.sections" :key="si" class="ve-card">
        <div class="ve-card-header">
          <span class="ve-card-title">Section {{ si + 1 }}</span>
          <div class="ve-card-actions">
            <button class="ve-btn ve-btn-sm" @click="moveSection(si, -1)" :disabled="si === 0" title="Move up">↑</button>
            <button class="ve-btn ve-btn-sm" @click="moveSection(si, 1)" :disabled="si === draft.sections.length - 1" title="Move down">↓</button>
            <button class="ve-btn ve-btn-sm ve-btn-danger" @click="removeSection(si)" title="Remove section">✕</button>
          </div>
        </div>

        <div class="ve-field">
          <label class="ve-label-sm">Heading</label>
          <input class="ve-input" v-model="sec.heading" :placeholder="`e.g. ${si + 1}. Introduction`" @input="emitDraft" />
        </div>
        <div class="ve-field">
          <label class="ve-label-sm">Description</label>
          <textarea class="ve-textarea" v-model="sec.description" placeholder="Brief section description" rows="2" @input="emitDraft"></textarea>
        </div>

        <div class="ve-sub-group">
          <div class="ve-sub-group-header">
            <label class="ve-label-sm">Elements</label>
            <button class="ve-btn ve-btn-xs" @click="addElement(si)">+ Add</button>
          </div>
          <div v-for="(el, ei) in sec.elements" :key="ei" class="ve-element-row">
            <select class="ve-select" v-model="el.type" @change="emitDraft">
              <option value="text">text</option>
              <option value="table">table</option>
              <option value="image">image</option>
            </select>
            <input class="ve-input ve-input-flex" v-model="el.description" placeholder="Describe the element content" @input="emitDraft" />
            <button class="ve-btn ve-btn-xs ve-btn-danger" @click="removeElement(si, ei)" title="Remove element">✕</button>
          </div>
        </div>

        <div class="ve-sub-group">
          <div class="ve-sub-group-header">
            <label class="ve-label-sm">Subsections</label>
            <button class="ve-btn ve-btn-xs" @click="addSubsection(si)">+ Add</button>
          </div>
          <div v-for="(sub, ti) in sec.subsections" :key="ti" class="ve-card ve-card-nested">
            <div class="ve-card-header">
              <span class="ve-card-title">Sub {{ ti + 1 }}</span>
              <button class="ve-btn ve-btn-sm ve-btn-danger" @click="removeSubsection(si, ti)" title="Remove subsection">✕</button>
            </div>
            <div class="ve-field">
              <label class="ve-label-sm">Heading</label>
              <input class="ve-input" v-model="sub.heading" :placeholder="`e.g. ${si + 1}.${ti + 1} Analysis`" @input="emitDraft" />
            </div>
            <div class="ve-field">
              <label class="ve-label-sm">Description</label>
              <textarea class="ve-textarea" v-model="sub.description" placeholder="Subsection description" rows="2" @input="emitDraft"></textarea>
            </div>
            <div class="ve-sub-group">
              <div class="ve-sub-group-header">
                <label class="ve-label-sm">Elements</label>
                <button class="ve-btn ve-btn-xs" @click="addSubElement(si, ti)">+ Add</button>
              </div>
              <div v-for="(el, ei) in sub.elements" :key="ei" class="ve-element-row">
                <select class="ve-select" v-model="el.type" @change="emitDraft">
                  <option value="text">text</option>
                  <option value="table">table</option>
                  <option value="image">image</option>
                </select>
                <input class="ve-input ve-input-flex" v-model="el.description" placeholder="Describe element content" @input="emitDraft" />
                <button class="ve-btn ve-btn-xs ve-btn-danger" @click="removeSubElement(si, ti, ei)" title="Remove element">✕</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, watch } from 'vue'
import * as jsyaml from 'js-yaml'

const props = defineProps({
  modelValue: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue'])

const defaultValue = () => ({
  title: '',
  sections: [],
})

const draft = reactive(defaultValue())

watch(() => props.modelValue, (val) => {
  if (!val) {
    Object.assign(draft, defaultValue())
    return
  }
  try {
    const parsed = jsyaml.load(val)
    if (parsed && typeof parsed === 'object') {
      const norm = normalize(parsed)
      Object.assign(draft, norm)
    }
  } catch {
    // Keep current draft on parse error
  }
}, { immediate: true })

function normalize(data) {
  const result = { title: '', sections: [] }
  if (data.title !== undefined) result.title = String(data.title)
  if (Array.isArray(data.sections)) {
    result.sections = data.sections.map(normalizeSection)
  }
  return result
}

function normalizeSection(sec) {
  return {
    heading: sec.heading || '',
    description: sec.description || '',
    elements: Array.isArray(sec.elements) ? sec.elements.map(e => ({
      type: ['text', 'table', 'image'].includes(e.type) ? e.type : 'text',
      description: e.description || '',
    })) : [],
    subsections: Array.isArray(sec.subsections) ? sec.subsections.map(normalizeSection) : [],
  }
}

function toYaml() {
  const obj = { title: draft.title, sections: [] }
  for (const sec of draft.sections) {
    const s = { heading: sec.heading, description: sec.description }
    if (sec.elements.length > 0) {
      s.elements = sec.elements.map(e => ({ type: e.type, description: e.description }))
    }
    if (sec.subsections.length > 0) {
      s.subsections = sec.subsections.map(sub => {
        const sb = { heading: sub.heading, description: sub.description }
        if (sub.elements.length > 0) {
          sb.elements = sub.elements.map(e => ({ type: e.type, description: e.description }))
        }
        return sb
      })
    }
    obj.sections.push(s)
  }
  return jsyaml.dump(obj, { indent: 2, lineWidth: -1, noRefs: true, quotingType: '"', forceQuotes: true })
}

function emitDraft() {
  emit('update:modelValue', toYaml())
}

function addSection() {
  draft.sections.push({ heading: '', description: '', elements: [], subsections: [] })
  emitDraft()
}

function removeSection(idx) {
  draft.sections.splice(idx, 1)
  emitDraft()
}

function moveSection(idx, dir) {
  const target = idx + dir
  if (target < 0 || target >= draft.sections.length) return
  const tmp = draft.sections[idx]
  draft.sections[idx] = draft.sections[target]
  draft.sections[target] = tmp
  emitDraft()
}

function addElement(si) {
  draft.sections[si].elements.push({ type: 'text', description: '' })
  emitDraft()
}

function removeElement(si, ei) {
  draft.sections[si].elements.splice(ei, 1)
  emitDraft()
}

function addSubsection(si) {
  draft.sections[si].subsections.push({ heading: '', description: '', elements: [] })
  emitDraft()
}

function removeSubsection(si, ti) {
  draft.sections[si].subsections.splice(ti, 1)
  emitDraft()
}

function addSubElement(si, ti) {
  draft.sections[si].subsections[ti].elements.push({ type: 'text', description: '' })
  emitDraft()
}

function removeSubElement(si, ti, ei) {
  draft.sections[si].subsections[ti].elements.splice(ei, 1)
  emitDraft()
}
</script>

<style scoped>
.visual-editor {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 16px;
  overflow-y: auto;
  padding: 4px 0;
}

.ve-field { display: flex; flex-direction: column; gap: 4px; }
.ve-label { font-size: 13px; font-weight: 600; color: var(--text-secondary); }
.ve-label-sm { font-size: 12px; font-weight: 500; color: var(--text-muted); }

.ve-input {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  padding: 8px 10px;
  font-family: inherit;
  font-size: 13px;
  outline: none;
  transition: border-color 0.2s;
}
.ve-input:focus { border-color: var(--accent-blue); }
.ve-input-flex { flex: 1; min-width: 0; }

.ve-textarea {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  padding: 8px 10px;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.5;
  resize: vertical;
  outline: none;
}
.ve-textarea:focus { border-color: var(--accent-blue); }

.ve-select {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  padding: 6px 8px;
  font-size: 12px;
  outline: none;
  cursor: pointer;
  flex-shrink: 0;
}
.ve-select:focus { border-color: var(--accent-blue); }

.ve-btn {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 12px;
  padding: 4px 10px;
  transition: all 0.2s;
  white-space: nowrap;
  flex-shrink: 0;
}
.ve-btn:hover:not(:disabled) { background: var(--bg-hover); color: var(--text-primary); border-color: var(--accent-blue); }
.ve-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.ve-btn-add { background: var(--accent-blue); color: #fff; border-color: var(--accent-blue); font-size: 13px; padding: 6px 14px; }
.ve-btn-add:hover { opacity: 0.9; }
.ve-btn-sm { font-size: 13px; padding: 2px 8px; line-height: 1.4; }
.ve-btn-xs { font-size: 11px; padding: 2px 8px; }
.ve-btn-danger { color: var(--accent-red); }
.ve-btn-danger:hover { background: rgba(217,83,79,0.15); border-color: var(--accent-red); color: var(--accent-red); }

.ve-card {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 8px;
}
.ve-card-nested {
  background: var(--bg-secondary);
  margin: 4px 0;
}
.ve-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.ve-card-title { font-size: 13px; font-weight: 600; color: var(--accent-cyan); }
.ve-card-actions { display: flex; gap: 4px; }

.ve-section-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.ve-group-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.ve-sub-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
}
.ve-sub-group-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.ve-element-row {
  display: flex;
  gap: 6px;
  align-items: center;
}

.ve-element-row .ve-input-flex {
  flex: 1;
}

@media (max-width: 768px) {
  .ve-element-row { flex-wrap: wrap; }
  .ve-card { padding: 8px; }
  .ve-sub-group { padding: 6px; }
}
</style>