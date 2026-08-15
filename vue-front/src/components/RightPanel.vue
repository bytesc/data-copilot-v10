<template>
  <div class="right-panel-inner">
    <div class="right-panel-header">Generated Files</div>
    <div v-if="files.length === 0" class="right-panel-empty">No files generated yet</div>
    <div v-else class="file-list">
      <div v-for="file in files" :key="file.id" class="file-item">
        <div class="file-title" :title="file.title">{{ file.title }}</div>
        <div class="file-actions">
          <a v-if="file.downloadUrlMd" :href="file.downloadUrlMd + '?download=1'" class="download-btn md" target="_blank">.md</a>
          <a v-if="file.downloadUrlDocx" :href="file.downloadUrlDocx + '?download=1'" class="download-btn docx" target="_blank">.docx</a>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  files: { type: Array, required: true },
})
</script>