import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Development only: every request starting with /api is forwarded to Flask (HTTPS, port 5050).
// "secure: false" skips certificate verification for this local proxy hop only.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'https://localhost:5050', changeOrigin: true, secure: false },
    },
  },
})
