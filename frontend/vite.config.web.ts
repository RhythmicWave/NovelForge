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
      '@renderer': resolve(__dirname, 'src/renderer/src')
    }
  },
  plugins: [
    vue(),
    {
      name: 'html-transform',
      transformIndexHtml(html) {
        // 更新 CSP 以允许连接到 GitHub API
        return html.replace(
          /<meta\s+http-equiv=["']Content-Security-Policy["'].*?>/i,
          '<meta http-equiv="Content-Security-Policy" content="default-src \'self\'; script-src \'self\' \'unsafe-inline\' \'wasm-unsafe-eval\'; connect-src \'self\' http://127.0.0.1:8000 https://api.github.com; style-src \'self\' \'unsafe-inline\';">'
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
