import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd())
  // Dev-only proxy target. Deliberately NOT a VITE_-prefixed variable so it is
  // never injected into the client bundle; the built app always talks to its own
  // origin and relies on nginx/front.py to proxy API and static file requests.
  const serverTarget = env.DEV_PROXY_TARGET

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
          changeOrigin: true,
        },
        '/upload-csv': {
          target: serverTarget,
          changeOrigin: true,
        },
        '/upload-txt': {
          target: serverTarget,
          changeOrigin: true,
        },
        '/tmp_imgs': {
          target: serverTarget,
          changeOrigin: true,
        }
      }
    }
  }
})