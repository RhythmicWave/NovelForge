#!/usr/bin/env node
// 将后端打包结果复制到 dist-web/backend 中，方便一并部署

const fs = require('fs')
const path = require('path')

function ensureDir(dir) {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true })
  }
}

function copyDir(src, dest) {
  if (!fs.existsSync(src)) {
    console.warn(`[postbuild-copy-backend] 源目录不存在，跳过复制: ${src}`)
    return
  }
  ensureDir(dest)
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const srcPath = path.join(src, entry.name)
    const destPath = path.join(dest, entry.name)
    if (entry.isDirectory()) {
      copyDir(srcPath, destPath)
    } else if (entry.isFile()) {
      fs.copyFileSync(srcPath, destPath)
    }
  }
}

function main() {
  const root = path.resolve(__dirname, '..')
  const frontendDistWeb = path.join(root, 'dist-web')
  const backendRoot = path.resolve(root, '..', 'backend')

  const backendDistSrc = path.join(backendRoot, 'dist')
  const backendEnv = path.join(backendRoot, '.env')
  const backendEnvExample = path.join(backendRoot, '.env.example')
  const backendDestRoot = path.join(frontendDistWeb, 'backend')

  if (!fs.existsSync(frontendDistWeb)) {
    console.warn('[postbuild-copy-backend] dist-web 目录不存在，是否已先运行 npm run build:web ?')
    return
  }

  console.log('[postbuild-copy-backend] 复制 backend/dist 到 dist-web/backend ...')
  copyDir(backendDistSrc, backendDestRoot)

  for (const startupScript of ['start-web.py', 'start-web.bat']) {
    fs.copyFileSync(path.join(__dirname, startupScript), path.join(frontendDistWeb, startupScript))
  }
  const indexPath = path.join(frontendDistWeb, 'index.html')
  const indexHtml = fs.readFileSync(indexPath, 'utf8')
  const runtimeScriptTag = '<script src="./backend-port.js"></script>'
  if (!indexHtml.includes(runtimeScriptTag)) {
    fs.writeFileSync(indexPath, indexHtml.replace('</head>', `  ${runtimeScriptTag}\n</head>`))
  }

  const envSource = fs.existsSync(backendEnv) ? backendEnv : backendEnvExample
  if (fs.existsSync(envSource)) {
    ensureDir(backendDestRoot)
    const destEnv = path.join(backendDestRoot, '.env')
    fs.copyFileSync(envSource, destEnv)
    console.log(
      `[postbuild-copy-backend] 已复制 ${path.basename(envSource)} 为 backend/.env`
    )
  } else {
    console.warn('[postbuild-copy-backend] 未找到 backend/.env.example，跳过 .env 复制')
  }

  console.log('[postbuild-copy-backend] 完成')
}

main()
