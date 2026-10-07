import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// During development, every request starting with /api is forwarded to Flask.
// This avoids CORS problems. Change the port if your colleague's Flask uses another one.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:5050', changeOrigin: true },
    },
  },
})
