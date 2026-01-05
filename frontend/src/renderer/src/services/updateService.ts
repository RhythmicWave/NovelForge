/**
 * GitHub Release 更新检测服务
 * 跨平台支持（Electron + Web）
 */

export interface ReleaseInfo {
  version: string
  name: string
  body: string // Release notes (Markdown)
  publishedAt: string
  htmlUrl: string
  downloadUrl?: string
}

export interface UpdateCheckResult {
  hasUpdate: boolean
  currentVersion: string
  latestVersion?: string
  releaseInfo?: ReleaseInfo
}

const GITHUB_REPO = 'RhythmicWave/NovelForge'
const GITHUB_API_BASE = 'https://api.github.com'
const REQUEST_TIMEOUT = 10000 // 10秒超时

/**
 * 从 package.json 获取当前版本号
 */
export function getCurrentVersion(): string {
  // 在构建时，版本号会被注入到 import.meta.env
  // 如果没有，则使用默认值
  return import.meta.env.VITE_APP_VERSION || '0.8.5'
}

/**
 * 比较版本号，支持诸如 0.8.5-fix2 这一类带后缀的 tag。
 * 规则：
 *   1) 先比较数字主版本（按 x.y.z 拆分）；
 *   2) 若主版本相同，带后缀的视为高于无后缀（0.8.5-fix2 > 0.8.5）；
 *   3) 若双方都有后缀，则尝试解析尾部数字进行比较（fix2 > fix1），否则按字符串比较。
 * @returns 1 if v1 > v2, -1 if v1 < v2, 0 if equal
 */
function compareVersions(v1: string, v2: string): number {
  const parseVersion = (v: string) => {
    const cleaned = v.replace(/^v/, '')
    const [core, suffixRaw] = cleaned.split('-', 2)
    const coreParts = core.split('.').map((s) => {
      const n = parseInt(s, 10)
      return Number.isNaN(n) ? 0 : n
    })
    return { coreParts, suffix: suffixRaw || '' }
  }

  const a = parseVersion(v1)
  const b = parseVersion(v2)

  // 1) 比较主版本号
  const maxLen = Math.max(a.coreParts.length, b.coreParts.length)
  for (let i = 0; i < maxLen; i++) {
    const num1 = a.coreParts[i] ?? 0
    const num2 = b.coreParts[i] ?? 0
    if (num1 > num2) return 1
    if (num1 < num2) return -1
  }

  // 2) 主版本相等时比较后缀
  if (a.suffix === b.suffix) return 0
  if (a.suffix && !b.suffix) return 1
  if (!a.suffix && b.suffix) return -1

  // 3) 双方都有后缀，优先比较尾部数字
  const re = /^([a-zA-Z\-]*)(\d*)$/
  const ma = a.suffix.match(re)
  const mb = b.suffix.match(re)
  if (ma && mb) {
    const labelA = ma[1]
    const labelB = mb[1]
    const numA = ma[2] ? parseInt(ma[2], 10) : 0
    const numB = mb[2] ? parseInt(mb[2], 10) : 0
    if (labelA === labelB && (numA !== numB)) {
      return numA > numB ? 1 : -1
    }
  }

  // 4) 回退到纯字符串比较
  if (a.suffix > b.suffix) return 1
  if (a.suffix < b.suffix) return -1
  return 0
}

/**
 * 带超时的 fetch
 */
async function fetchWithTimeout(url: string, timeout: number): Promise<Response> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeout)
  
  try {
    const response = await fetch(url, {
      signal: controller.signal,
      headers: {
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'NovelForge-App'
      }
    })
    clearTimeout(timeoutId)
    return response
  } catch (error) {
    clearTimeout(timeoutId)
    throw error
  }
}

/**
 * 获取最新的 GitHub Release
 */
async function fetchLatestRelease(timeout: number = REQUEST_TIMEOUT): Promise<ReleaseInfo | null> {
  const url = `${GITHUB_API_BASE}/repos/${GITHUB_REPO}/releases/latest`
  
  try {
    const response = await fetchWithTimeout(url, timeout)
    
    if (!response.ok) {
      // 对于 HTTP 错误，抛出异常而不是当成「没有更新」，
      // 这样上层可以给出明确的错误提示（例如 403 速率限制）。
      if (response.status === 403) {
        throw new Error('GitHub API 访问受限 (403)，可能已达到未登录用户的速率限制，请稍后重试')
      }
      throw new Error(`GitHub API 返回错误: ${response.status}`)
    }
    
    const data = await response.json()
    
    return {
      version: data.tag_name?.replace(/^v/, '') || data.name,
      name: data.name || data.tag_name,
      body: data.body || '',
      publishedAt: data.published_at,
      htmlUrl: data.html_url,
      downloadUrl: data.assets?.[0]?.browser_download_url
    }
  } catch (error: any) {
    if (error.name === 'AbortError') {
      throw new Error('请求超时')
    }
    throw error
  }
}

/**
 * 检查更新（带重试机制）
 * @param maxRetries 最大重试次数（0 表示不重试）
 */
export async function checkForUpdates(maxRetries: number = 0): Promise<UpdateCheckResult> {
  const currentVersion = getCurrentVersion()
  let lastError: Error | null = null
  
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      const releaseInfo = await fetchLatestRelease()
      
      if (!releaseInfo) {
        return {
          hasUpdate: false,
          currentVersion
        }
      }
      
      const hasUpdate = compareVersions(releaseInfo.version, currentVersion) > 0
      
      return {
        hasUpdate,
        currentVersion,
        latestVersion: releaseInfo.version,
        releaseInfo: hasUpdate ? releaseInfo : undefined
      }
    } catch (error: any) {
      lastError = error
      console.warn(`更新检测失败 (尝试 ${attempt + 1}/${maxRetries + 1}):`, error.message)
      
      // 如果还有重试机会，等待一段时间后重试
      if (attempt < maxRetries) {
        await new Promise(resolve => setTimeout(resolve, 2000 * (attempt + 1)))
      }
    }
  }
  
  // 所有重试都失败
  throw lastError || new Error('更新检测失败')
}

/**
 * 自动检查更新（带1次重试）
 */
export async function autoCheckForUpdates(): Promise<UpdateCheckResult> {
  return checkForUpdates(1)
}

/**
 * 手动检查更新（不重试）
 */
export async function manualCheckForUpdates(): Promise<UpdateCheckResult> {
  return checkForUpdates(0)
}
