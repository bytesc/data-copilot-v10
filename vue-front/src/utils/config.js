import { reactive } from 'vue'

export const configState = reactive({
  enable_mcp: true,
  enable_base_knowledge: true,
  enable_web_search: true,
  enable_fetch_url: true,
  enable_target_knowledge: false,
  enable_edit: true,
  _loaded: false,
})

export async function loadConfig() {
  if (configState._loaded) return configState
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
}

export const enableEdit = () => configState.enable_edit
