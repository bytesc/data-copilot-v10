<template>
  <div class="knowledge-page">
    <div class="page-header">
      <router-link to="/" class="back-link">← Back to Chat</router-link>
      <h2>Knowledge Management</h2>
    </div>
    <nav class="sub-nav">
      <router-link
        v-for="tab in tabs"
        :key="tab.path"
        :to="tab.path"
        class="sub-nav-link"
        active-class="sub-nav-link-active"
      >
        <span class="sub-nav-icon">{{ tab.icon }}</span>
        {{ tab.label }}
      </router-link>
    </nav>
    <div class="sub-page-content">
      <router-view />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const enableBaseKnowledge = ref(true)
const tabs = ref([
  { path: '/knowledge/base-knowledge', icon: '📚', label: 'Base Knowledge' },
  { path: '/knowledge/brief-info', icon: '📝', label: 'Brief Info' },
  { path: '/knowledge/guides', icon: '📋', label: 'Guides' },
])

onMounted(async () => {
  try {
    const res = await fetch('/api/config')
    if (res.ok) {
      const cfg = await res.json()
      enableBaseKnowledge.value = cfg.enable_base_knowledge
      if (!cfg.enable_base_knowledge) {
        tabs.value = tabs.value.filter(t => t.path !== '/knowledge/base-knowledge')
        if (router.currentRoute.value.path === '/knowledge/base-knowledge') {
          router.replace('/knowledge/brief-info')
        }
      }
    }
  } catch (_) { /* ignore */ }
})
</script>

<style scoped>
.knowledge-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.page-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 24px;
  border-bottom: 1px solid var(--border-color);
  background: var(--bg-secondary);
  flex-shrink: 0;
}

.page-header h2 {
  font-size: 18px;
  color: var(--text-primary);
}

.sub-nav {
  display: flex;
  gap: 2px;
  padding: 0 24px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.sub-nav-link {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 16px;
  color: var(--text-secondary);
  text-decoration: none;
  font-size: 13px;
  border-bottom: 2px solid transparent;
  transition: all 0.2s;
  white-space: nowrap;
}

.sub-nav-link:hover {
  color: var(--text-primary);
  background: var(--bg-hover);
}

.sub-nav-link-active {
  color: var(--accent-blue);
  border-bottom-color: var(--accent-blue);
}

.sub-nav-icon {
  font-size: 14px;
}

.sub-page-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
}

.back-link {
  color: var(--accent-blue);
  text-decoration: none;
  font-size: 14px;
  white-space: nowrap;
}

.back-link:hover {
  text-decoration: underline;
}

@media (max-width: 768px) {
  .page-header {
    padding: 12px 16px;
  }

  .page-header h2 {
    font-size: 16px;
  }

  .sub-nav {
    padding: 0 12px;
    overflow-x: auto;
  }

  .sub-nav-link {
    padding: 8px 12px;
    font-size: 12px;
  }
}
</style>