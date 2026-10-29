import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In development the UI runs on :5173 and the FastAPI back end on :8000.
// The production build (frontend/dist) is served by FastAPI itself.
export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})
