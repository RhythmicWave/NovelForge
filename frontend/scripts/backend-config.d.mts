export const DEFAULT_BACKEND_PORT: number

export function loadBackendPort(options?: { env?: NodeJS.ProcessEnv; envFiles?: string[] }): number
