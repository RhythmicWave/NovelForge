import { spawnSync } from 'node:child_process'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { loadBackendPort } from './backend-config.mjs'

const frontendDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const backendPort = loadBackendPort({
  envFiles: [resolve(frontendDir, '../backend/.env')]
})
const cliPath = resolve(frontendDir, 'node_modules/openapi-typescript/bin/cli.js')
const result = spawnSync(
  process.execPath,
  [
    cliPath,
    `http://127.0.0.1:${backendPort}/openapi.json`,
    '-o',
    resolve(frontendDir, 'src/renderer/src/types/generated.d.ts')
  ],
  { stdio: 'inherit' }
)

if (result.error) throw result.error
process.exitCode = result.status ?? 1
