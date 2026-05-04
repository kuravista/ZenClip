import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3987,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:9478',
        changeOrigin: true,
      },
      '/status': {
        target: 'http://127.0.0.1:9478',
        changeOrigin: true,
      },
      '/process': {
        target: 'http://127.0.0.1:9478',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://127.0.0.1:9478',
        changeOrigin: true,
      },
    },
  },
})
