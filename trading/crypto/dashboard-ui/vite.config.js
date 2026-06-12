import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 3007,
    proxy: {
      '/api': 'http://127.0.0.1:3006',
      '/live_state.json': 'http://127.0.0.1:3006',
    },
  },
  build: {
    outDir: '../dashboard',
    emptyOutDir: true,
  },
})
