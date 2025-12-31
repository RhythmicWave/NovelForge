export function setupWebMock() {
  if (typeof window === 'undefined') return

  // @ts-ignore
  if (!window.electron) {
    console.log('Initializing Web Mock for Electron...')
    // @ts-ignore
    window.electron = {
      process: {
        versions: {
          electron: 'web',
          chrome: navigator.userAgent,
          node: 'web'
        }
      },
      ipcRenderer: {
        invoke: async (channel: string, ...args: any[]) => {
          console.log(`[WebMock] invoke ${channel}`, args)
          return undefined
        },
        on: (channel: string, _listener: any) => {
           console.log(`[WebMock] on ${channel}`)
           return undefined
        },
        send: (channel: string, ...args: any[]) => {
           console.log(`[WebMock] send ${channel}`, args)
        },
        removeListener: () => {},
        removeAllListeners: () => {}
      }
    }
  }

  // @ts-ignore
  if (!window.api) {
    console.log('Initializing Web Mock for API...')
    // @ts-ignore
    window.api = {
      setApiKey: async (id: number, apiKey: string) => {
        console.log(`[WebMock] setApiKey ${id}`)
        localStorage.setItem(`api_key_${id}`, apiKey)
        return { success: true }
      },
      getApiKey: async (id: number) => {
        console.log(`[WebMock] getApiKey ${id}`)
        const key = localStorage.getItem(`api_key_${id}`)
        return { success: true, apiKey: key || undefined }
      },
      openIdeasHome: async () => {
        console.log(`[WebMock] openIdeasHome`)
        window.open('/#/ideas-home', '_blank')
        return { success: true }
      }
    }
  }
}
