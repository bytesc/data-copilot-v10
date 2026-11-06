import { reactive } from 'vue'
import { isErrorNotified, markErrorAsNotified } from './errors.js'

export const toasts = reactive([])

const MAX_TOASTS = 5
const MAX_MESSAGE_LENGTH = 300
const DEDUPE_WINDOW = 1500
const DURATIONS = {
  error: 6000,
  warning: 5000,
  success: 3000,
  info: 3500,
}

const timers = new Map()
const recent = new Map()
let nextId = 0

function truncate(text) {
  const message = String(text ?? '')
  return message.length > MAX_MESSAGE_LENGTH
    ? `${message.slice(0, MAX_MESSAGE_LENGTH)}...`
    : message
}

export function showToast(message, type = 'info', options = {}) {
  const text = truncate(message).trim()
  if (!text) return null

  const dedupeKey = `${type}:${text}`
  const now = Date.now()
  const lastShownAt = recent.get(dedupeKey)
  if (!options.force && lastShownAt && now - lastShownAt < DEDUPE_WINDOW) {
    return null
  }
  recent.set(dedupeKey, now)

  const id = ++nextId
  toasts.push({ id, type, message: text })
  while (toasts.length > MAX_TOASTS) {
    dismissToast(toasts[0].id)
  }

  const duration = options.duration ?? DURATIONS[type] ?? DURATIONS.info
  if (duration > 0) {
    timers.set(id, setTimeout(() => dismissToast(id), duration))
  }
  return id
}

export function dismissToast(id) {
  const index = toasts.findIndex((toast) => toast.id === id)
  if (index !== -1) toasts.splice(index, 1)

  const timer = timers.get(id)
  if (timer) {
    clearTimeout(timer)
    timers.delete(id)
  }
}

export function showErrorToast(message, options) {
  return showToast(message, 'error', options)
}

export function showWarningToast(message, options) {
  return showToast(message, 'warning', options)
}

export function showSuccessToast(message, options) {
  return showToast(message, 'success', options)
}

export function showInfoToast(message, options) {
  return showToast(message, 'info', options)
}

export function notifyError(error, fallback = 'Request failed') {
  if (isErrorNotified(error)) return null

  const message =
    typeof error === 'string'
      ? error
      : error?.name === 'ApiError'
        ? error.message
        : fallback

  const id = showErrorToast(message || fallback)
  markErrorAsNotified(error)
  return id
}
