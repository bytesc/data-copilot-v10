<template>
  <div class="app-container">
    <nav class="top-nav">
      <div class="nav-brand">
        <router-link to="/" class="nav-logo">Data-Copilot</router-link>
      </div>
      <div class="nav-links">
        <router-link to="/" class="nav-link" active-class="nav-link-active">
          <span class="nav-icon">💬</span> Chat
        </router-link>
        <router-link to="/data" class="nav-link" active-class="nav-link-active">
          <span class="nav-icon">📊</span> Data
        </router-link>
      </div>
    </nav>

    <div class="page-content">
      <router-view />
    </div>

    <IcpArea />

    <button class="theme-toggle" :title="isDark ? '切换到亮色主题' : '切换到暗色主题'" @click="toggleTheme">
      <svg v-if="isDark" viewBox="0 0 24 24">
        <circle cx="12" cy="12" r="4"></circle>
        <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"></path>
      </svg>
      <svg v-else viewBox="0 0 24 24">
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
      </svg>
    </button>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import IcpArea from '@/components/IcpArea.vue'

const isDark = ref(true)

function applyTheme() {
  const theme = isDark.value ? 'dark' : 'light'
  document.documentElement.setAttribute('data-theme', theme)
  localStorage.setItem('theme', theme)
}

function toggleTheme() {
  isDark.value = !isDark.value
  applyTheme()
}

onMounted(() => {
  const saved = localStorage.getItem('theme')
  isDark.value = saved !== 'light'
  applyTheme()
})
</script>

<style scoped>
.top-nav {
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 0 24px;
  height: 48px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.nav-brand {
  display: flex;
  align-items: center;
}

.nav-logo {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
  text-decoration: none;
}

.nav-links {
  display: flex;
  align-items: center;
  gap: 4px;
}

.nav-link {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  text-decoration: none;
  font-size: 13px;
  transition: all 0.2s;
}

.nav-link:hover {
  color: var(--text-primary);
  background: var(--bg-hover);
}

.nav-link-active {
  color: var(--accent-blue);
  background: var(--bg-tertiary);
}

.nav-icon {
  font-size: 14px;
}

.page-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
}

@media (max-width: 768px) {
  .top-nav {
    padding: 0 12px;
    gap: 8px;
  }

  .nav-logo {
    font-size: 14px;
  }

  .nav-link {
    padding: 6px 10px;
    font-size: 12px;
  }
}
</style>