<template>
  <div class="tools-page">
    <div class="page-header">
      <h2>🔧 Available Tools</h2>
    </div>
    <nav class="sub-nav">
      <button
        class="sub-nav-link"
        :class="{ active: activeTab === 'functions' }"
        @click="activeTab = 'functions'"
      >🐍 Python Functions</button>
      <button
        v-if="enableMcp"
        class="sub-nav-link"
        :class="{ active: activeTab === 'mcp' }"
        @click="activeTab = 'mcp'"
      >🔌 MCP Tools</button>
    </nav>
    <div class="page-body">
      <div v-if="loading" class="loading-text">Loading tools...</div>
      <div v-else-if="error" class="error-text">{{ error }}</div>
      <template v-else>
        <div v-if="activeTab === 'functions'">
          <div v-if="pythonFunctions.length === 0" class="empty-text">No Python functions available</div>
          <div v-else class="tool-grid">
            <div v-for="fn in pythonFunctions" :key="fn.name" class="tool-card">
              <div class="tool-name">{{ fn.name }}</div>
              <div class="tool-desc">{{ fn.description }}</div>
            </div>
          </div>
        </div>
        <div v-if="activeTab === 'mcp'">
          <div v-if="loadingMcp" class="loading-text">Loading MCP tools...</div>
          <div v-else-if="mcpServers.length === 0" class="empty-text">No MCP servers configured</div>
          <div v-else>
            <div v-for="srv in mcpServers" :key="srv.server_name" class="mcp-server-card">
              <div class="server-header">
                <span class="server-name">{{ srv.server_name }}</span>
                <span class="server-url">{{ srv.url }}</span>
              </div>
              <div class="server-desc">{{ srv.server_description }}</div>
              <div v-if="srv.error" class="server-error">⚠️ Connection failed: {{ srv.error }}</div>
              <div v-else-if="srv.tools.length === 0" class="empty-text">No tools reported by this server</div>
              <div v-else class="tool-grid">
                <div v-for="tool in srv.tools" :key="tool.name" class="tool-card">
                  <div class="tool-name">{{ tool.name }}</div>
                  <div class="tool-desc">{{ tool.description }}</div>
                  <div v-if="tool.parameters && tool.parameters.length" class="tool-params">
                    Parameters: {{ tool.parameters.join(', ') }}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const enableMcp = ref(true)
const activeTab = ref('functions')
const pythonFunctions = ref([])
const mcpServers = ref([])
const loading = ref(true)
const loadingMcp = ref(true)
const error = ref('')

onMounted(async () => {
  try {
    const cfgRes = await fetch('/api/config')
    if (cfgRes.ok) {
      const cfg = await cfgRes.json()
      enableMcp.value = cfg.enable_mcp
    }
  } catch (_) { /* ignore */ }
  try {
    const funcRes = await fetch('/api/tools/functions')
    if (funcRes.ok) {
      pythonFunctions.value = await funcRes.json()
    }
  } catch (e) {
    error.value = `Functions load failed: ${e.message}`
  } finally {
    loading.value = false
  }

  fetch('/api/tools/mcp').then(res => {
    if (res.ok) return res.json()
    throw new Error(`HTTP ${res.status}`)
  }).then(data => {
    mcpServers.value = data
  }).catch(e => {
    mcpServers.value = [{ server_name: 'MCP', error: `Load failed: ${e.message}` }]
  }).finally(() => {
    loadingMcp.value = false
  })
})
</script>

<style scoped>
.tools-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.page-header {
  padding: 16px 24px;
  border-bottom: 1px solid var(--border-color);
  background: var(--bg-secondary);
  flex-shrink: 0;
}

.page-header h2 {
  font-size: 18px;
  color: var(--text-primary);
  margin: 0;
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
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.sub-nav-link:hover {
  color: var(--text-primary);
  background: var(--bg-hover);
}

.sub-nav-link.active {
  color: var(--accent-blue);
  border-bottom-color: var(--accent-blue);
}

.page-body {
  flex: 1;
  padding: 16px 24px;
  overflow-y: auto;
}

.tool-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tool-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
  padding: 12px 16px;
}

.tool-name {
  font-family: var(--font-mono);
  font-size: 14px;
  font-weight: 600;
  color: var(--accent-cyan);
  margin-bottom: 4px;
}

.tool-desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.4;
  white-space: pre-wrap;
}

.tool-params {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 6px;
  font-family: var(--font-mono);
}

.mcp-server-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
  padding: 14px 16px;
  margin-bottom: 12px;
}

.server-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 6px;
}

.server-name {
  font-size: 14px;
  font-weight: 700;
  color: var(--accent-blue);
}

.server-url {
  font-size: 12px;
  color: var(--text-muted);
  font-family: var(--font-mono);
}

.server-desc {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.server-error {
  font-size: 13px;
  color: var(--accent-red);
  padding: 6px 10px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-sm);
}

.loading-text {
  font-size: 14px;
  color: var(--text-muted);
  padding: 24px;
  text-align: center;
}

.error-text {
  font-size: 14px;
  color: var(--accent-red);
  padding: 24px;
  text-align: center;
}

.empty-text {
  font-size: 13px;
  color: var(--text-muted);
  padding: 12px;
  font-style: italic;
}
</style>