export function setupWebMock(): void {
  if (typeof window === 'undefined') return
  if (!window.electron) {
    console.log('Initializing Web Mock for Electron...')
    window.electron = {
      process: {
        platform: 'web',
        env: {},
        versions: {
          electron: 'web',
          chrome: navigator.userAgent,
          node: 'web'
        }
      },
      webUtils: {
        getPathForFile: (file: File) => {
          console.log(`[WebMock] getPathForFile`, file)
          return URL.createObjectURL(file)
        }
      },
      webFrame: {
        setZoomLevel: (level: number) => {
          console.log(`[WebMock] setZoomLevel ${level}`)
        },
        insertCSS: (css: string): string => {
          console.log(`[WebMock] insertCSS ${css}`)
          return css
        },
        setZoomFactor: (factor: number) => {
          console.log(`[WebMock] setZoomFactor ${factor}`)
        }
      },
      ipcRenderer: {
        invoke: async (channel: string, ...args: unknown[]) => {
          console.log(`[WebMock] invoke ${channel}`, args)
          return undefined
        },
        on: (channel: string, _listener: unknown) => {
          console.log(`[WebMock] on ${channel}, and ${_listener}`)
          return () => {}
        },
        once: (channel: string, _listener: unknown) => {
          console.log(`[WebMock] once ${channel}, and ${_listener}`)
          return () => {}
        },
        postMessage: (channel: string, message: unknown, transfer?: unknown[]) => {
          console.log(`[WebMock] postMessage ${channel}`, message, transfer)
        },
        send: (channel: string, ...args: unknown[]) => {
          console.log(`[WebMock] send ${channel}`, args)
        },
        sendSync: (channel: string, ...args: unknown[]) => {
          console.log(`[WebMock] sendSync ${channel}`, args)
          return undefined
        },
        sendTo: (webContentsId: number, channel: string, ...args: unknown[]) => {
          console.log(`[WebMock] sendTo ${webContentsId} ${channel}`, args)
        },
        sendToHost: (channel: string, ...args: unknown[]) => {
          console.log(`[WebMock] sendToHost ${channel}`, args)
        },
        removeListener: (channel: string, listener: (...args: unknown[]) => void) => {
          console.log(`[WebMock] removeListener ${channel} and ${listener}`)
          return window.electron.ipcRenderer
        },
        removeAllListeners: () => {}
      }
    }
  }
  if (!window.api) {
    console.log('Initializing Web Mock for API...')
    window.api = {
      setApiKey: async (id: number) => {
        console.log(`[WebMock] setApiKey ${id}`)
        return { success: true }
      },
      getApiKey: async (id: number) => {
        console.log(`[WebMock] getApiKey ${id}`)
        return { success: true, apiKey: undefined }
      },
      openIdeasHome: async () => {
        console.log(`[WebMock] openIdeasHome`)
        window.open('/#/ideas-home', '_blank')
        return { success: true }
      }
    }
  }
}
