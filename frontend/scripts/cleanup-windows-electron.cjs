const fs = require('node:fs/promises')
const path = require('node:path')

const stagedElectronDir = path.join(__dirname, '..', 'dist', '.electron-base')

module.exports = async () => {
  // 该目录仅用于打包前写入 Windows 图标，所有构建产物生成后即可删除。
  await fs.rm(stagedElectronDir, { recursive: true, force: true })
}
