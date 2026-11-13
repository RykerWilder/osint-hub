import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// In sviluppo (npm run dev) le chiamate /api vengono inoltrate al backend locale.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: process.env.API_URL || 'http://localhost:8000', changeOrigin: true },
    },
  },
  build: { chunkSizeWarningLimit: 700 },
})
