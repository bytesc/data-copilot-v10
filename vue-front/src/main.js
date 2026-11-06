import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import { configState } from './utils/config.js'
import { markErrorAsNotified } from './utils/errors.js'
import { notifyError, showErrorToast } from './utils/toast.js'
import './assets/styles/main.css'

function buildLlmMeta() {
  if (!configState.current_model) return null
  return {
    model: configState.current_model,
    reasoning_effort: configState.current_reasoning_effort || '',
    style: configState.current_style || '',
    use_images: !!configState.use_images,
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

function reportHttpError(response) {
  showErrorToast(String(response.status))
}

function installFetchErrorInterceptor(nativeFetch) {
  return function (input, init) {
    const isRequest = typeof Request !== 'undefined' && input instanceof Request
    const silent = !!(init && init.silentError)
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
    const requestInput = isRequest ? new Request(input, options) : input
    const requestOptions = isRequest ? undefined : options

    return nativeFetch(requestInput, requestOptions)
      .then((response) => {
        if (!response.ok && !silent) {
          reportHttpError(response)
        }
        return response
      })
      .catch((error) => {
        if (error?.name === 'AbortError') throw error
        if (!silent) {
          showErrorToast('Network error')
          markErrorAsNotified(error)
        }
        throw error
      })
  }
}

if (!window.__llmEnvelopeFetchInstalled) {
  window.__llmEnvelopeFetchInstalled = true
  const nativeFetch = window.fetch.bind(window)
  window.fetch = installFetchErrorInterceptor(nativeFetch)
}

if (!window.__unhandledRejectionToastInstalled) {
  window.__unhandledRejectionToastInstalled = true
  window.addEventListener('unhandledrejection', (event) => {
    const reason = event.reason
    if (reason?.name === 'AbortError') return
    notifyError(reason, 'Unexpected error')
  })
}

createApp(App).use(router).mount('#app')
