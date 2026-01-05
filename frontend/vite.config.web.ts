import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  root: 'src/renderer',
  base: './',
  resolve: {
    alias: {
      '@renderer': resolve(__dirname, 'src/renderer/src')
    }
  },
  plugins: [
    vue(),
    {
      name: 'html-transform',
      transformIndexHtml(html) {
        // 开发模式下移除 CSP，避免阻止样式和脚本加载
        return html.replace(/<meta\s+http-equiv=["']Content-Security-Policy["'].*?>/i, '')
      }
    }
  ],
  server: {
    port: 5173,
    proxy: {
        '/api': {
            target: 'http://127.0.0.1:8000',
            changeOrigin: true,
        },
        '/imgs': {
            target: 'http://127.0.0.1:8000',
            changeOrigin: true,
        }
    }
  },
  build: {
    outDir: '../../dist-web',
    emptyOutDir: true
  }
})
