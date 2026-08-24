function validateBackendPort(value: unknown, source: string): number {
  const port = Number(value)
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error(`Invalid backend port from ${source}: ${String(value)}`)
  }
  return port
}

const runtimePort = typeof window !== 'undefined' ? window.api?.backendPort : undefined

export const BACKEND_PORT =
  runtimePort !== undefined
    ? validateBackendPort(runtimePort, 'Electron runtime configuration')
    : validateBackendPort(import.meta.env.VITE_BACKEND_PORT, 'build configuration')

export const LOCAL_BACKEND_BASE_URL = `http://127.0.0.1:${BACKEND_PORT}`
