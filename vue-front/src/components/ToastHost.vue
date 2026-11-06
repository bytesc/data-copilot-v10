<template>
  <div class="toast-host" aria-live="polite" aria-atomic="false">
    <TransitionGroup name="toast">
      <div
        v-for="toast in toasts"
        :key="toast.id"
        :class="['toast', `toast-${toast.type}`]"
        role="alert"
      >
        <span class="toast-icon" aria-hidden="true">
          <svg v-if="toast.type === 'error'" viewBox="0 0 24 24">
            <circle cx="12" cy="12" r="9"></circle>
            <path d="M12 8v5"></path>
            <path d="M12 16h.01"></path>
          </svg>
          <svg v-else-if="toast.type === 'success'" viewBox="0 0 24 24">
            <circle cx="12" cy="12" r="9"></circle>
            <path d="M8.5 12.5l2.5 2.5 4.5-5"></path>
          </svg>
          <svg v-else-if="toast.type === 'warning'" viewBox="0 0 24 24">
            <path d="M12 3.5L21 19.5H3z"></path>
            <path d="M12 9v4"></path>
            <path d="M12 16.5h.01"></path>
          </svg>
          <svg v-else viewBox="0 0 24 24">
            <circle cx="12" cy="12" r="9"></circle>
            <path d="M12 11v5"></path>
            <path d="M12 8h.01"></path>
          </svg>
        </span>

        <div class="toast-body">
          <div class="toast-title">{{ titleFor(toast.type) }}</div>
          <div class="toast-message">{{ toast.message }}</div>
        </div>

        <button class="toast-close" type="button" aria-label="Dismiss" @click="dismissToast(toast.id)">
          <svg viewBox="0 0 24 24">
            <path d="M6 6l12 12M18 6L6 18"></path>
          </svg>
        </button>
      </div>
    </TransitionGroup>
  </div>
</template>

<script setup>
import { toasts, dismissToast } from '@/utils/toast.js'

const TITLES = {
  error: 'Error',
  success: 'Success',
  warning: 'Warning',
  info: 'Notice',
}

function titleFor(type) {
  return TITLES[type] || TITLES.info
}
</script>

<style scoped>
.toast-host {
  position: fixed;
  top: 60px;
  right: 20px;
  z-index: 4000;
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: min(420px, calc(100vw - 32px));
  pointer-events: none;
}

.toast {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-left: 4px solid var(--accent-blue);
  border-radius: var(--radius-sm);
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.32);
  pointer-events: auto;
}

.toast-error {
  border-left-color: var(--accent-red);
}

.toast-success {
  border-left-color: var(--accent-green);
}

.toast-warning {
  border-left-color: var(--accent-orange);
}

.toast-info {
  border-left-color: var(--accent-cyan);
}

.toast-icon {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  margin-top: 1px;
  color: var(--accent-blue);
}

.toast-error .toast-icon {
  color: var(--accent-red);
}

.toast-success .toast-icon {
  color: var(--accent-green);
}

.toast-warning .toast-icon {
  color: var(--accent-orange);
}

.toast-info .toast-icon {
  color: var(--accent-cyan);
}

.toast-icon svg {
  width: 18px;
  height: 18px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.toast-body {
  flex: 1;
  min-width: 0;
}

.toast-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-secondary);
  margin-bottom: 3px;
}

.toast-message {
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-primary);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 220px;
  overflow-y: auto;
}

.toast-close {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  background: none;
  border: none;
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  cursor: pointer;
}

.toast-close:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.toast-close svg {
  width: 14px;
  height: 14px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
}

.toast-enter-active,
.toast-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateX(16px);
}

.toast-move {
  transition: transform 0.2s ease;
}

@media (max-width: 768px) {
  .toast-host {
    top: 56px;
    right: 12px;
    width: calc(100vw - 24px);
  }
}
</style>
