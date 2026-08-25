const BASE_URL = import.meta.env.VITE_API_BASE || '/api'

export async function fetchSessions(limit = 50) {
  const res = await fetch(`${BASE_URL}/sessions/?limit=${limit}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const data = await res.json()
  return data.sessions || []
}

export async function fetchSessionHistory(sessionId) {
  const res = await fetch(`${BASE_URL}/session/${sessionId}/history`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function fetchGeneratedFiles(sessionId) {
  const res = await fetch(`${BASE_URL}/session/${sessionId}/generated-files`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const data = await res.json()
  return data.files || []
}

export async function logUserInput(sessionId, cycleIndex, userInput) {
  await fetch(`${BASE_URL}/log-user-input/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, cycle_index: cycleIndex, user_input: userInput }),
  })
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
            const json = JSON.parse(line.slice(6))
            yield json
          } catch {
            // skip malformed JSON
          }
        }
      }
    }
  }

  if (buffer.trim()) {
    for (const line of buffer.split('\n')) {
      if (line.startsWith('data: ')) {
        try {
          const json = JSON.parse(line.slice(6))
          yield json
        } catch {
          // skip
        }
      }
    }
  }
}