import { reactive } from 'vue'

export const configState = reactive({
  enable_mcp: true,
  enable_base_knowledge: true,
  enable_web_search: true,
  enable_fetch_url: true,
  enable_target_knowledge: false,
  enable_edit: true,
  models: [],
  current_model: '',
  current_reasoning_effort: '',
  _loaded: false,
})

let _loadPromise = null

export async function loadConfig() {
  if (configState._loaded) return configState
  if (_loadPromise) return _loadPromise
  _loadPromise = (async () => {
    configState._loaded = true
    try {
      const res = await fetch('/api/config')
      if (res.ok) {
        const cfg = await res.json()
        Object.assign(configState, cfg)
      }
    } catch (_) {
      /* ignore */
    }
    return configState
  })()
  try {
    return await _loadPromise
  } finally {
    _loadPromise = null
  }
}

export const enableEdit = () => configState.enable_edit

const MODEL_STORAGE_KEY = 'data-copilot-selected-model'
const EFFORT_STORAGE_PREFIX = 'data-copilot-reasoning-effort:'

function effortStorageKey(modelId) {
  return `${EFFORT_STORAGE_PREFIX}${modelId}`
}

function getSavedReasoningEffort(modelId) {
  return localStorage.getItem(effortStorageKey(modelId))
}

let _effortTouched = false

export async function selectModel(modelId) {
  if (!modelId) return false
  try {
    const res = await fetch('/api/models/select/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: modelId }),
    })
    if (!res.ok) return false
    const data = await res.json()
    configState.models = data.models || configState.models
    configState.current_model = data.current_model
    configState.current_reasoning_effort = data.current_reasoning_effort ?? ''
    localStorage.setItem(MODEL_STORAGE_KEY, data.current_model)
    localStorage.setItem(
      effortStorageKey(data.current_model),
      configState.current_reasoning_effort,
    )
    return true
  } catch (_) {
    return false
  }
}

export async function selectReasoningEffort(value) {
  _effortTouched = true
  try {
    const res = await fetch('/api/models/reasoning-effort/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ value: value || '' }),
    })
    if (!res.ok) return false
    const data = await res.json()
    configState.models = data.models || configState.models
    configState.current_model = data.current_model || configState.current_model
    configState.current_reasoning_effort = data.current_reasoning_effort ?? ''
    localStorage.setItem(
      effortStorageKey(configState.current_model),
      configState.current_reasoning_effort,
    )
    return true
  } catch (_) {
    return false
  }
}

export function getSavedModelId() {
  return localStorage.getItem(MODEL_STORAGE_KEY) || ''
}

export async function restoreSavedModel() {
  await loadConfig()
  const saved = getSavedModelId()
  if (!saved) return
  if (!configState.models.some(m => m.id === saved)) return
  if (configState.current_model !== saved) {
    await selectModel(saved)
  }
  if (_effortTouched) return
  const savedEffort = getSavedReasoningEffort(saved)
  if (savedEffort !== null && savedEffort !== configState.current_reasoning_effort) {
    await selectReasoningEffort(savedEffort)
  }
}
