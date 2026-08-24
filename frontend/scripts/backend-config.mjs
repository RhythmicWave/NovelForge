import { existsSync, readFileSync } from 'node:fs'

export const DEFAULT_BACKEND_PORT = 54321

function parsePort(value, source) {
  const normalized = String(value).trim()
  if (!/^\d+$/.test(normalized)) {
    throw new Error(`APP_PORT in ${source} must be an integer between 1 and 65535`)
  }

  const port = Number(normalized)
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error(`APP_PORT in ${source} must be an integer between 1 and 65535`)
  }
  return port
}

function readEnvValue(content, key) {
  for (const line of content.split(/\r?\n/)) {
    const match = line.match(/^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$/)
    if (!match || match[1] !== key) continue

    let value = match[2]
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1)
    } else {
      value = value.replace(/\s+#.*$/, '').trim()
    }
    return value
  }
  return undefined
}

export function loadBackendPort({ env = process.env, envFiles = [] } = {}) {
  if (env.APP_PORT !== undefined && env.APP_PORT !== '') {
    return parsePort(env.APP_PORT, 'process environment')
  }

  for (const envFile of envFiles) {
    if (!existsSync(envFile)) continue
    const value = readEnvValue(readFileSync(envFile, 'utf8'), 'APP_PORT')
    if (value !== undefined && value !== '') {
      return parsePort(value, envFile)
    }
  }

  return DEFAULT_BACKEND_PORT
}
