const fs = require('node:fs/promises')
const path = require('node:path')
const { Data, NtExecutable, NtExecutableResource, Resource } = require('resedit')

const projectDir = path.resolve(__dirname, '..')
const electronSourceDir = path.join(projectDir, 'node_modules', 'electron', 'dist')
const stagedElectronDir = path.join(projectDir, 'dist', '.electron-base', 'win32-x64')
const iconPath = path.join(projectDir, 'build', 'icon.ico')

function getVersionStrings(appInfo) {
  const values = {
    FileDescription: appInfo.description || appInfo.productName,
    ProductName: appInfo.productName,
    LegalCopyright: appInfo.copyright,
    InternalName: appInfo.productFilename,
    OriginalFilename: '',
  }
  if (appInfo.companyName) {
    values.CompanyName = appInfo.companyName
  }
  return values
}

async function setWindowsExecutableResources(executablePath, appInfo) {
  const [executableData, iconData] = await Promise.all([
    fs.readFile(executablePath),
    fs.readFile(iconPath),
  ])
  const executable = NtExecutable.from(executableData)
  const resources = NtExecutableResource.from(executable)
  const versionInfo = Resource.VersionInfo.fromEntries(resources.entries)
  const iconGroup = resources.entries.find((entry) => entry.type === 14)

  if (versionInfo.length !== 1 || !iconGroup) {
    throw new Error('Electron executable is missing its version or icon resource.')
  }

  const language = versionInfo[0].getAllLanguagesForStringValues()[0] || { lang: 1033, codepage: 1200 }
  versionInfo[0].setStringValues(language, getVersionStrings(appInfo))
  versionInfo[0].setFileVersion(appInfo.shortVersion || appInfo.buildVersion, language.lang)
  versionInfo[0].setProductVersion(
    appInfo.shortVersionWindows || appInfo.getVersionInWeirdWindowsForm(),
    language.lang,
  )
  versionInfo[0].outputToResourceEntries(resources.entries)

  const iconFile = Data.IconFile.from(iconData)
  Resource.IconGroupEntry.replaceIconsForResource(
    resources.entries,
    iconGroup.id,
    iconGroup.lang,
    iconFile.icons.map((item) => item.data),
  )
  resources.outputResource(executable)
  await fs.writeFile(executablePath, Buffer.from(executable.generate()))
}

module.exports = async (context) => {
  if (process.env.NOVELFORGE_PREEDIT_WIN_EXE !== 'true' || context.electronPlatformName !== 'win32') {
    return
  }

  await fs.rm(stagedElectronDir, { recursive: true, force: true })
  await fs.cp(electronSourceDir, stagedElectronDir, { recursive: true })
  await setWindowsExecutableResources(path.join(stagedElectronDir, 'electron.exe'), context.packager.appInfo)

  // 在 electron-builder 注入 ASAR 完整性数据前，为暂存的可执行文件写入图标。
  context.packager.config.electronDist = stagedElectronDir
}
