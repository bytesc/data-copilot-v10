import { reactive, watch } from 'vue'

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
  current_style: '',
  _loaded: false,
})

const STORAGE_KEY = 'data-copilot-llm-config'
const LEGACY_SELECTION_KEY = 'data-copilot-llm-selection'
const LEGACY_MODEL_KEY = 'data-copilot-selected-model'
const LEGACY_EFFORT_PREFIX = 'data-copilot-reasoning-effort:'
const LEGACY_STYLE_PREFIX = 'data-copilot-style:'

function storageGet(key) {
  try {
    return localStorage.getItem(key)
  } catch (_) {
    return null
  }
}

function storageSet(key, value) {
  try {
    localStorage.setItem(key, String(value))
  } catch (_) {
    /* ignore */
  }
}

function normalizeModels(models) {
  if (!Array.isArray(models)) return []
  return models.map(m => ({
    id: m?.id || '',
    name: m?.name || '',
    model: m?.model || '',
    url: m?.url || '',
    reasoning_effort_options: Array.isArray(m?.reasoning_effort_options)
      ? [...m.reasoning_effort_options]
      : [],
    style_options: Array.isArray(m?.style_options) ? [...m.style_options] : [],
  }))
}

function normalizeSelection(selection) {
  if (!selection || typeof selection !== 'object') return null
  const model = typeof selection.model === 'string' ? selection.model : ''
  if (!model) return null
  return {
    model,
    reasoning_effort:
      typeof selection.reasoning_effort === 'string' ? selection.reasoning_effort : '',
    style: typeof selection.style === 'string' ? selection.style : '',
  }
}

function readLegacySelection() {
  try {
    const raw = storageGet(LEGACY_SELECTION_KEY)
    if (raw) {
      const saved = normalizeSelection(JSON.parse(raw))
      if (saved) return saved
    }
  } catch (_) {
    /* ignore */
  }

  const model = storageGet(LEGACY_MODEL_KEY) || ''
  if (!model) return null
  return {
    model,
    reasoning_effort: storageGet(`${LEGACY_EFFORT_PREFIX}${model}`) ?? '',
    style: storageGet(`${LEGACY_STYLE_PREFIX}${model}`) ?? '',
  }
}

function readStored() {
  try {
    const raw = storageGet(STORAGE_KEY)
    if (raw) {
      const data = JSON.parse(raw)
      if (data && typeof data === 'object') {
        return {
          models: normalizeModels(data.models),
          selected: normalizeSelection(data.selected),
        }
      }
    }
  } catch (_) {
    /* ignore */
  }
  return { models: [], selected: readLegacySelection() }
}

function findModel(models, modelId) {
  return models.find(m => m.id === modelId)
}

function defaultSelection(models) {
  const model = models[0]
  return {
    model: model?.id || '',
    reasoning_effort: model?.reasoning_effort_options?.[0] || '',
    style: '',
  }
}

function isSelectionValid(selection, models) {
  if (!selection) return false
  const model = findModel(models, selection.model)
  if (!model) return false
  if (
    selection.reasoning_effort !== '' &&
    !model.reasoning_effort_options.includes(selection.reasoning_effort)
  ) {
    return false
  }
  if (selection.style !== '' && !model.style_options.includes(selection.style)) {
    return false
  }
  return true
}

function resolveSelection(selection, models) {
  return isSelectionValid(selection, models) ? selection : defaultSelection(models)
}

function applySelection(selection) {
  configState.current_model = selection.model
  configState.current_reasoning_effort = selection.reasoning_effort
  configState.current_style = selection.style
}

function saveStore() {
  storageSet(
    STORAGE_KEY,
    JSON.stringify({
      models: normalizeModels(configState.models),
      selected: {
        model: configState.current_model,
        reasoning_effort: configState.current_reasoning_effort || '',
        style: configState.current_style || '',
      },
    }),
  )
}

const initialStore = readStored()
configState.models = initialStore.models
applySelection(resolveSelection(initialStore.selected, initialStore.models))

let _persistEnabled = true

watch(
  () => [
    configState.current_model,
    configState.current_reasoning_effort,
    configState.current_style,
  ],
  () => {
    if (_persistEnabled) saveStore()
  },
  { flush: 'sync' },
)

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
        const backendModels = normalizeModels(cfg.models)
        const stored = readStored()
        const listChanged =
          stored.models.length > 0 &&
          JSON.stringify(stored.models) !== JSON.stringify(backendModels)
        const selection = listChanged
          ? defaultSelection(backendModels)
          : resolveSelection(stored.selected, backendModels)

        _persistEnabled = false
        try {
          Object.assign(configState, cfg)
          configState.models = backendModels
          applySelection(selection)
        } finally {
          _persistEnabled = true
        }
        saveStore()
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

function currentModelConfig() {
  return findModel(configState.models, configState.current_model)
}

export async function selectModel(modelId) {
  const model = findModel(configState.models, modelId)
  if (!model) return false
  applySelection({
    model: model.id,
    reasoning_effort: model.reasoning_effort_options[0] || '',
    style: '',
  })
  return true
}

export async function selectReasoningEffort(value) {
  const model = currentModelConfig()
  if (!model) return false
  const effort = value || ''
  if (effort && !model.reasoning_effort_options.includes(effort)) return false
  configState.current_reasoning_effort = effort
  return true
}

export async function selectStyle(value) {
  const model = currentModelConfig()
  if (!model) return false
  const style = value || ''
  if (style && !model.style_options.includes(style)) return false
  configState.current_style = style
  return true
}

export function getSavedModelId() {
  return readStored().selected?.model || ''
}

export async function restoreSavedModel() {
  await loadConfig()
}
