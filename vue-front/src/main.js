import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import { configState } from './utils/config.js'
import './assets/styles/main.css'

const nativeFetch = window.fetch.bind(window)

window.fetch = function (input, init) {
  const isRequest = typeof Request !== 'undefined' && input instanceof Request
  const url = isRequest ? input.url : String(input)
  const headers = new Headers(
    init?.headers || (isRequest ? input.headers : undefined),
  )

  if (configState.current_model) {
    headers.set('X-LLM-Model', configState.current_model)
    if (!url.includes('/api/models/select/')) {
      headers.set(
        'X-LLM-Reasoning-Effort',
        configState.current_reasoning_effort || '',
      )
      headers.set('X-LLM-Style', configState.current_style || '')
    }
  }

  const options = { ...(init || {}), headers }
  if (isRequest) {
    return nativeFetch(new Request(input, options))
  }
  return nativeFetch(input, options)
}

createApp(App).use(router).mount('#app')