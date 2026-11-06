export class ApiError extends Error {
  constructor(message, { status = 0, payload = null, url = '' } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.payload = payload
    this.url = url
  }
}

export function markErrorAsNotified(error) {
  if (error && typeof error === 'object') {
    try {
      error.__toastNotified = true
    } catch (_) {
      /* ignore */
    }
  }
  return error
}

export function isErrorNotified(error) {
  return !!(error && typeof error === 'object' && error.__toastNotified)
}
