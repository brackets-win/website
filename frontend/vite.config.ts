import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

/** Set `VITE_USE_POLLING=1` if file saves don’t trigger HMR (some network drives / VMs). */
const usePolling = process.env.VITE_USE_POLLING === '1'

const djangoTarget = 'http://127.0.0.1:8000'

/** Preserve Host (localhost:3000) so Django session cookies match the page origin. */
const bracketsProxy = {
  '/brackets': {
    target: djangoTarget,
    changeOrigin: false,
  },
  '/media': {
    target: djangoTarget,
    changeOrigin: false,
  },
} as const

// https://vitejs.dev/config/
export default defineConfig(({ command }) => ({
  plugins: [react()],
  base: command === 'build' ? '/static/' : '/',
  server: {
    host: '127.0.0.1',
    port: 3000,
    /** If 3000 is taken (e.g. another `npm run dev`), Vite tries 3001, 3002, … */
    strictPort: false,
    proxy: bracketsProxy,
    watch: usePolling ? { usePolling: true, interval: 300 } : undefined,
    /** Avoid stale HTML/JS when the browser caches localhost aggressively. */
    headers: {
      'Cache-Control': 'no-store',
    },
  },
  preview: {
    port: 3000,
    strictPort: false,
    proxy: bracketsProxy,
  },
}))
