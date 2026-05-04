import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'
import { readFileSync } from 'fs'

const backendOrigin = process.env.VITE_DEV_BACKEND_URL || 'http://127.0.0.1:54321'

// 读取 package.json 中的版本号
const packageJson = JSON.parse(readFileSync(resolve(__dirname, 'package.json'), 'utf-8'))
const version = packageJson.version

export default defineConfig({
  root: 'src/renderer',
  base: './',
  define: {
    'import.meta.env.VITE_APP_VERSION': JSON.stringify(version)
  },
  resolve: {
    alias: {
      '@renderer': resolve(__dirname, 'src/renderer/src'),
      '@': resolve(__dirname, 'src/renderer/src')
    }
  },
  plugins: [
    vue(),
    {
      name: 'html-transform',
      transformIndexHtml(html) {
        return html.replace(
          /<meta\s+http-equiv=["']Content-Security-Policy["'][\s\S]*?>/i,
          '<meta http-equiv="Content-Security-Policy" content="' +
          "default-src 'self'; " +
          "script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'; " +
          "style-src 'self' 'unsafe-inline'; " +
          "connect-src 'self' https://api.github.com; img-src 'self' data:;" +
          '">'
        )
      }
    }
  ],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: backendOrigin,
        changeOrigin: true
      },
      '/imgs': {
        target: backendOrigin,
        changeOrigin: true
      }
    }
  },
  build: {
    outDir: '../../dist-web',
    emptyOutDir: true
  }
})
