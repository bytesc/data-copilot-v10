import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig(({ mode }) => {
  // Dev-only proxy target. Deliberately NOT a VITE_-prefixed variable so it is
  // never injected into the client bundle; the built app always talks to its own
  // origin and relies on nginx/front.py to proxy API and static file requests.
  // loadEnv's default 'VITE_' prefix would hide DEV_PROXY_TARGET, so it is listed
  // explicitly (this does not expose it to the client — only VITE_* is injected).
  // loadEnv applies process.env after .env files, so the containerized dev
  // workflow (Dockerfile.dev) overrides the baked value with
  // `-e DEV_PROXY_TARGET=http://host.docker.internal:8008`.
  const env = loadEnv(mode, process.cwd(), ['VITE_', 'DEV_PROXY_TARGET'])
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