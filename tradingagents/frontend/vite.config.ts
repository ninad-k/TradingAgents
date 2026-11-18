import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3009,
    proxy: {
      '/api': 'http://localhost:8009',
      '/ws': {
        target: 'ws://localhost:8009',
        ws: true
      }
    }
  }
})
