import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'
import { readFileSync } from 'fs'

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
        // 更新 CSP：
        // - 允许连接 GitHub API
        // - 放宽 connect-src，支持访问任意后端主机（方便局域网 / 服务器部署）
        return html.replace(
          /<meta\s+http-equiv=["']Content-Security-Policy["'].*?>/i,
          '<meta http-equiv="Content-Security-Policy" content="' +
          "default-src 'self'; " +
          "script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'; " +
          "style-src 'self' 'unsafe-inline'; " +
          // 这里使用 connect-src *，方便本地和局域网部署；如果将来需要更严格策略可再收紧
          "connect-src * https://api.github.com;" +
          '">'
        )
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