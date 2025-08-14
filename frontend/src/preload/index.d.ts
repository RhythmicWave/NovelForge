import { ElectronAPI } from '@electron-toolkit/preload'

interface Api {
  setApiKey: (id: number, apiKey: string) => Promise<{ success: boolean; error?: string }>
  getApiKey: (id: number) => Promise<{ success: boolean; apiKey?: string; error?: string }>
  openChapterStudio: (projectId: number, chapterCardId: number) => Promise<{ success: boolean }>
}

declare global {
  interface Window {
    electron: ElectronAPI
    api: Api
  }
}
