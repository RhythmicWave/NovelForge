/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_APP_PLATFORM: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
