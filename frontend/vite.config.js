import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The Django API runs on 127.0.0.1:8000; CORS is enabled on the backend for
// this dev origin, so the app calls the API directly (no proxy needed).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
  },
})
