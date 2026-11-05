import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import { configState } from './utils/config.js'
import './assets/styles/main.css'

function buildLlmMeta() {
  if (!configState.current_model) return null
  return {
    model: configState.current_model,
    reasoning_effort: configState.current_reasoning_effort || '',
    style: configState.current_style || '',
  }
}

function wrapJsonBody(body, meta) {
  if (typeof body !== 'string') return body
  let payload
  try {
    payload = JSON.parse(body)
  } catch (_) {
    return body
  }
  if (
    payload &&
    typeof payload === 'object' &&
    !Array.isArray(payload) &&
    payload.meta &&
    Object.prototype.hasOwnProperty.call(payload, 'data')
  ) {
    payload.meta = { ...(meta || {}), ...payload.meta }
    return JSON.stringify(payload)
  }
  return JSON.stringify({ meta: meta || {}, data: payload })
}

if (!window.__llmEnvelopeFetchInstalled) {
  window.__llmEnvelopeFetchInstalled = true
  const nativeFetch = window.fetch.bind(window)

  window.fetch = function (input, init) {
    const isRequest = typeof Request !== 'undefined' && input instanceof Request
    const headers = new Headers(
      init?.headers || (isRequest ? input.headers : undefined),
    )
    const meta = buildLlmMeta()
    let body = init?.body

    if (typeof body === 'string') {
      body = wrapJsonBody(body, meta)
    } else if (typeof FormData !== 'undefined' && body instanceof FormData && meta) {
      if (!body.has('meta')) {
        body.append('meta', JSON.stringify(meta))
      }
    }

    const options = { ...(init || {}), headers, body }
    if (isRequest) {
      return nativeFetch(new Request(input, options))
    }
    return nativeFetch(input, options)
  }
}

createApp(App).use(router).mount('#app')