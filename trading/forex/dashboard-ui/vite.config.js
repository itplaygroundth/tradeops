import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'
import { resolve } from 'path'

export default defineConfig({
  server: {
    port: 3004,
    proxy: {
      '/api/mt5': 'http://localhost:5001',
    },
  },
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      injectRegister: 'script',
      includeAssets: ['fox_logo.jpg'],
      manifest: {
        name: 'AI Trading Positions',
        short_name: 'AI Trade',
        description: 'AI Trading Live — Positions & Agents',
        theme_color: '#0B0E11',
        background_color: '#0B0E11',
        display: 'standalone',
        orientation: 'portrait',
        start_url: '/positions.html',
        icons: [
          { src: '/fox_logo.jpg', sizes: '192x192', type: 'image/jpeg' },
          { src: '/fox_logo.jpg', sizes: '512x512', type: 'image/jpeg' },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,jpg,png}'],
        runtimeCaching: [
          {
            urlPattern: /live_state\.json/,
            handler: 'NetworkFirst',
            options: { cacheName: 'live-data', networkTimeoutSeconds: 3 },
          },
        ],
      },
    }),
  ],
  build: {
    outDir: '../dashboard',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),
      },
      output: {
        manualChunks: { 'vendor-react': ['react', 'react-dom'] },
      },
    },
    sourcemap: false,
    minify: 'esbuild',
    cssMinify: true,
    cssCodeSplit: true,
  },
})
