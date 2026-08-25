import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd())
  const serverTarget = env.VITE_SERVER_URL || 'http://127.0.0.1:8009'

  return {
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
          target: serverTarget,
          changeOrigin: true
        },
        '/upload-csv': {
          target: serverTarget,
          changeOrigin: true
        },
        '/upload-txt': {
          target: serverTarget,
          changeOrigin: true
        },
        '/tmp_imgs': {
          target: serverTarget,
          changeOrigin: true
        }
      }
    }
  }
})