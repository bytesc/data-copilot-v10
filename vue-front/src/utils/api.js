import { ApiError, isErrorNotified, markErrorAsNotified } from './errors.js'

const BASE_URL = import.meta.env.VITE_API_BASE || '/api'

async function request(url, init) {
  const response = await fetch(url, init)
  if (!response.ok) {
    let payload = null
    try {
      payload = await response.json()
    } catch (_) {
      /* non-JSON error body */
    }
    const error = new ApiError(payload?.error || String(response.status), {
      status: response.status,
      payload,
      url,
    })
    markErrorAsNotified(error)
    throw error
  }
  return response
}

export async function fetchSessions(limit = 50, includeDeleted = false) {
  const res = await request(
    `${BASE_URL}/sessions/?limit=${limit}&include_deleted=${includeDeleted ? 'true' : 'false'}`,
  )
  const data = await res.json()
  return data.sessions || []
}

export async function fetchWebAccessLogs(limit = 200, accessType = '', sessionId = '') {
  const params = new URLSearchParams({ limit: String(limit) })
  if (accessType) params.set('access_type', accessType)
  if (sessionId) params.set('session_id', sessionId)
  const res = await request(`${BASE_URL}/web-access-logs/?${params.toString()}`)
  const data = await res.json()
  return data.logs || []
}

export async function fetchWebAccessLogDetail(id) {
  const res = await request(`${BASE_URL}/web-access-log/${encodeURIComponent(id)}`)
  const data = await res.json()
  return data.log
}

export async function deleteSession(sessionId) {
  const res = await request(`${BASE_URL}/session/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
  })
  return res.json()
}

export async function restoreSession(sessionId) {
  const res = await request(
    `${BASE_URL}/session/${encodeURIComponent(sessionId)}/restore`,
    { method: 'POST' },
  )
  return res.json()
}

export async function fetchSessionHistory(sessionId) {
  const res = await request(`${BASE_URL}/session/${sessionId}/history`)
  return res.json()
}

export async function fetchGeneratedFiles(sessionId) {
  const res = await request(`${BASE_URL}/session/${sessionId}/generated-files`)
  const data = await res.json()
  return data.files || []
}

export function thinkStream(payload) {
  return createSSEStream(`${BASE_URL}/think/stream/`, payload)
}

export function actionStream(payload) {
  return createSSEStream(`${BASE_URL}/action/stream/`, payload)
}

export function actStream(payload) {
  return createSSEStream(`${BASE_URL}/act/stream/`, payload)
}

export function observeStream(payload) {
  return createSSEStream(`${BASE_URL}/observe/stream/`, payload)
}

export function generateDocumentStream(payload) {
  return createSSEStream(`${BASE_URL}/generate-document/stream/`, payload)
}

export function generateDocumentUnifiedStream(payload) {
  return createSSEStream(`${BASE_URL}/generate-document/stream/unified/`, payload)
}

function parseSSELine(line) {
  if (!line.startsWith('data: ')) return null
  try {
    return JSON.parse(line.slice(6))
  } catch (_) {
    return null
  }
}

async function* createSSEStream(url, payload) {
  let response
  try {
    response = await request(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  } catch (error) {
    yield {
      type: 'error',
      content: error?.message || 'Request failed',
      silent: isErrorNotified(error),
      status: error?.status || 0,
      code: error?.payload?.code || '',
    }
    return
  }

  const reader = response.body?.getReader()
  if (!reader) {
    yield { type: 'error', content: 'Request failed' }
    return
  }

  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const parts = buffer.split('\n\n')
      buffer = parts.pop()

      for (const part of parts) {
        for (const line of part.split('\n')) {
          const event = parseSSELine(line)
          if (event) yield event
        }
      }
    }

    if (buffer.trim()) {
      for (const line of buffer.split('\n')) {
        const event = parseSSELine(line)
        if (event) yield event
      }
    }
  } catch (error) {
    yield {
      type: 'error',
      content: error?.message || 'Request failed',
      silent: isErrorNotified(error),
    }
  } finally {
    try {
      reader.releaseLock()
    } catch (_) {
      /* ignore */
    }
  }
}
