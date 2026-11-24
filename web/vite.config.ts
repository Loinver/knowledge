import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 4010,
    // E2E 用 KG_API_PROXY_TARGET 指向隔离 API 端口，默认本地开发 :4000
    proxy: {
      '/api': {
        target: process.env.KG_API_PROXY_TARGET ?? 'http://127.0.0.1:4000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        // 共享运行时单独成块，业务代码随路由加载。
        manualChunks: {
          'vue-vendor': ['vue', 'vue-router', 'vue-i18n', 'pinia', 'axios'],
          'd3-vendor': ['d3-hierarchy', 'd3-force'],
        },
      },
    },
  },
})
