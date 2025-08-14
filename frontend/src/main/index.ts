import { app, shell, BrowserWindow, session, ipcMain } from 'electron'
import { join } from 'path'
import { electronApp, optimizer, is } from '@electron-toolkit/utils'
import icon from '../../resources/icon.png?asset'
import keytar from 'keytar'

const KEYTAR_SERVICE_NAME = 'NovelCreationEditor-LLM'

const studioWindows = new Map<string, BrowserWindow>()

function createWindow(): void {
  // Create the browser window.
  const mainWindow = new BrowserWindow({
    width: 900,
    height: 670,
    show: false,
    autoHideMenuBar: true,
    ...(process.platform === 'linux' ? { icon } : {}),
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false
    }
  })

  mainWindow.on('ready-to-show', () => {
    mainWindow.show()
  })

  mainWindow.webContents.setWindowOpenHandler((details) => {
    shell.openExternal(details.url)
    return { action: 'deny' }
  })

  // HMR for renderer base on electron-vite cli.
  // Load the remote URL for development or the local html file for production.
  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    mainWindow.loadURL(process.env['ELECTRON_RENDERER_URL'])
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }
  // Modify Content Security Policy
  session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
    callback({
      responseHeaders: {
        ...details.responseHeaders,
        'Content-Security-Policy': ["default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self' http://127.0.0.1:8000"]
      }
    })
  })
}

function openChapterStudio(projectId: number, chapterCardId: number) {
  const key = `${projectId}:${chapterCardId}`
  const existing = studioWindows.get(key)
  if (existing && !existing.isDestroyed()) {
    existing.focus()
    return
  }
  const win = new BrowserWindow({
    width: 1100,
    height: 760,
    show: true,
    title: 'Chapter Studio',
    autoHideMenuBar: true,
    ...(process.platform === 'linux' ? { icon } : {}),
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false
    }
  })
  studioWindows.set(key, win)
  win.on('closed', () => studioWindows.delete(key))

  const hash = `#/chapter-studio?projectId=${projectId}&cardId=${chapterCardId}`
  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    win.loadURL(process.env['ELECTRON_RENDERER_URL'] + hash)
  } else {
    win.loadFile(join(__dirname, '../renderer/index.html'), { hash })
  }
}

// This method will be called when Electron has finished
// initialization and is ready to create browser windows.
// Some APIs can only be used after this event occurs.
app.whenReady().then(() => {
  // Set app user model id for windows
  electronApp.setAppUserModelId('com.electron')

  // Default open or close DevTools by F12 in development
  // and ignore CommandOrControl + R in production.
  // see https://github.com/alex8088/electron-toolkit/tree/master/packages/utils
  app.on('browser-window-created', (_, window) => {
    optimizer.watchWindowShortcuts(window)
  })

  // IPC test
  ipcMain.on('ping', () => console.log('pong'))

  // Securely handle API keys
  ipcMain.handle('secure:set-api-key', async (_, { id, apiKey }) => {
    try {
      await keytar.setPassword(KEYTAR_SERVICE_NAME, String(id), apiKey)
      return { success: true }
    } catch (error) {
      console.error('Failed to set API key:', error)
      return { success: false, error: (error as Error).message }
    }
  })

  ipcMain.handle('secure:get-api-key', async (_, { id }) => {
    try {
      const apiKey = await keytar.getPassword(KEYTAR_SERVICE_NAME, String(id))
      return { success: true, apiKey }
    } catch (error) {
      console.error('Failed to get API key:', error)
      return { success: false, error: (error as Error).message }
    }
  })

  ipcMain.handle('chapter:open-studio', async (_, { projectId, chapterCardId }) => {
    openChapterStudio(projectId, chapterCardId)
    return { success: true }
  })

  createWindow()

  app.on('activate', function () {
    // On macOS it's common to re-create a window in the app when the
    // dock icon is clicked and there are no other windows open.
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

// Quit when all windows are closed, except on macOS. There, it's common
// for applications and their menu bar to stay active until the user quits
// explicitly with Cmd + Q.
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

// In this file you can include the rest of your app's specific main process
// code. You can also put them in separate files and require them here.
