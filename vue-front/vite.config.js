import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8009',
        changeOrigin: true
      },
      '/upload-csv': {
        target: 'http://127.0.0.1:8009',
        changeOrigin: true
      },
      '/upload-txt': {
        target: 'http://127.0.0.1:8009',
        changeOrigin: true
      },
      '/tmp_imgs': {
        target: 'http://127.0.0.1:8009',
        changeOrigin: true
      }
    }
  }
})