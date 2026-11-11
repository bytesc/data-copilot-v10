import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd())
  // Dev-only proxy target. Deliberately NOT a VITE_-prefixed variable so it is
  // never injected into the client bundle; the built app always talks to its own
  // origin and relies on nginx/front.py to proxy API and static file requests.
  // loadEnv() only returns VITE_* keys, so the containerized dev workflow
  // (Dockerfile.dev) overrides the baked .env value through the process
  // environment instead: `-e DEV_PROXY_TARGET=http://host.docker.internal:8008`.
  const serverTarget = process.env.DEV_PROXY_TARGET || env.DEV_PROXY_TARGET

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