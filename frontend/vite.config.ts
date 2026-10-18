import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const backend = 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/health': backend,
      '/rules': backend,
      '/samples': backend,
      '/review': backend,
      '/annotations': backend,
      '/reviews': backend,
      '/report': backend,
    },
  },
})
