import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    // E2E 用 KG_API_PROXY_TARGET 指向隔离 API 端口，默认本地开发 :8000
    proxy: {
      '/api': {
        target: process.env.KG_API_PROXY_TARGET ?? 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        // 拆分大块：naive-ui 与 vue 全家桶各自成块，业务代码随路由加载
        manualChunks: {
          'naive-ui': ['naive-ui'],
          'vue-vendor': ['vue', 'vue-router', 'vue-i18n', 'pinia', 'axios'],
          'd3-vendor': ['d3-hierarchy', 'd3-force'],
        },
      },
    },
  },
})
