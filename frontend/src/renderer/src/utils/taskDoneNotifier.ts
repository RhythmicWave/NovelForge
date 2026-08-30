export type DesktopNotificationPermission = NotificationPermission | 'unsupported'
export type TaskDoneNotificationPermission = DesktopNotificationPermission
export type DesktopNotificationMode = 'none' | 'failed_only' | 'all'

export type TaskDoneNotifyOptions = {
  taskId?: string
  title?: string
  body?: string
  enableSound?: boolean
  enableDesktopNotification?: boolean
  soundEnabled?: boolean
  desktopNotificationEnabled?: boolean
  desktopNotificationMode?: DesktopNotificationMode
}

type AudioContextConstructor = typeof AudioContext

const DUPLICATE_WINDOW_MS = 800
const recentTaskDoneMap = new Map<string, number>()

function getAudioContextConstructor(): AudioContextConstructor | undefined {
  if (typeof window === 'undefined') return undefined

  const audioWindow = window as Window &
    typeof globalThis & {
      webkitAudioContext?: AudioContextConstructor
    }

  return audioWindow.AudioContext ?? audioWindow.webkitAudioContext
}

export function isDesktopNotificationSupported(): boolean {
  return typeof window !== 'undefined' && 'Notification' in window
}

export async function requestDesktopNotificationPermission(): Promise<DesktopNotificationPermission> {
  if (!isDesktopNotificationSupported()) return 'unsupported'

  if (Notification.permission === 'granted') return 'granted'
  if (Notification.permission === 'denied') return 'denied'

  try {
    return await Notification.requestPermission()
  } catch {
    return Notification.permission
  }
}

export async function requestTaskDoneNotificationPermission(): Promise<TaskDoneNotificationPermission> {
  return requestDesktopNotificationPermission()
}

function safeShowDesktopNotification(title: string, body?: string): void {
  if (!isDesktopNotificationSupported()) return
  if (Notification.permission !== 'granted') return

  try {
    new Notification(title, {
      body,
      silent: true
    })
  } catch {
    /* noop */
  }
}

let sharedAudioContext: AudioContext | null = null

function getOrCreateAudioContext(): AudioContext | null {
  if (typeof window === 'undefined') return null
  const AudioContextClass = getAudioContextConstructor()
  if (!AudioContextClass) return null
  if (!sharedAudioContext || sharedAudioContext.state === 'closed') {
    try {
      sharedAudioContext = new AudioContextClass()
    } catch {
      return null
    }
  }
  return sharedAudioContext
}

export async function warmupDoneSound(): Promise<boolean> {
  try {
    const ctx = getOrCreateAudioContext()
    if (!ctx) return false
    if (ctx.state === 'suspended') {
      await ctx.resume()
    }
    return ctx.state === 'running'
  } catch {
    return false
  }
}

export async function unlockTaskDoneSound(): Promise<boolean> {
  return warmupDoneSound()
}

function playSingleTone(
  ctx: AudioContext,
  frequency: number,
  startAt: number,
  duration: number,
): void {
  const osc = ctx.createOscillator()
  const gain = ctx.createGain()

  osc.type = 'sine'
  osc.frequency.setValueAtTime(frequency, startAt)

  // 使用平滑稳定的线性渐变包络，避免极端值与时间异常
  gain.gain.setValueAtTime(0.0001, startAt)
  gain.gain.linearRampToValueAtTime(0.35, startAt + 0.02)
  gain.gain.linearRampToValueAtTime(0.0001, startAt + duration)

  osc.connect(gain)
  gain.connect(ctx.destination)

  osc.start(startAt)
  osc.stop(startAt + duration + 0.03)
}

async function safePlayChime(frequencies: [number, number]): Promise<boolean> {
  try {
    const ctx = getOrCreateAudioContext()
    if (!ctx) return false

    if (ctx.state === 'suspended') {
      await ctx.resume()
    }
    if (ctx.state !== 'running') {
      return false
    }

    const now = ctx.currentTime + 0.02
    playSingleTone(ctx, frequencies[0], now, 0.16)
    playSingleTone(ctx, frequencies[1], now + 0.18, 0.22)
    return true
  } catch (err) {
    console.warn('[TaskDoneNotifier] 播放提示音失败:', err)
    return false
  }
}

function safePlayDoneSound(): Promise<boolean> {
  return safePlayChime([440, 588])
}

function safePlayFailedSound(): Promise<boolean> {
  // 降调双音，与完成音（升调）区分
  return safePlayChime([440, 330])
}

export async function playTaskDoneSound(): Promise<boolean> {
  return safePlayDoneSound()
}

function isDuplicateTaskDone(taskId?: string): boolean {
  if (!taskId) return false

  const now = Date.now()
  const lastNotifyTime = recentTaskDoneMap.get(taskId) ?? 0

  if (now - lastNotifyTime < DUPLICATE_WINDOW_MS) return true

  recentTaskDoneMap.set(taskId, now)
  return false
}

/** 共享通知分发：统一去重、声音、桌面通知逻辑 */
function _dispatchNotification(
  options: TaskDoneNotifyOptions,
  defaults: { title: string; duplicatePrefix: string; playSound: () => Promise<boolean>; matchModes: DesktopNotificationMode[] },
): void {
  try {
    const {
      taskId,
      title = defaults.title,
      body,
      enableSound,
      enableDesktopNotification,
      soundEnabled,
      desktopNotificationEnabled,
      desktopNotificationMode,
    } = options

    const duplicateKey = `${defaults.duplicatePrefix}${taskId || `${title}\n${body || ''}`}`
    if (isDuplicateTaskDone(duplicateKey)) return

    if (enableSound ?? soundEnabled ?? false) {
      void defaults.playSound()
    }

    const mode = desktopNotificationMode ?? ((enableDesktopNotification ?? desktopNotificationEnabled) ? 'all' : 'none')
    if (defaults.matchModes.includes(mode)) {
      safeShowDesktopNotification(title, body)
    }
  } catch {
    /* noop */
  }
}

export function notifyTaskDone(options: TaskDoneNotifyOptions = {}): void {
  _dispatchNotification(options, {
    title: '任务已完成',
    duplicatePrefix: '',
    playSound: safePlayDoneSound,
    matchModes: ['all'],
  })
}

export function notifyTaskFailed(options: TaskDoneNotifyOptions = {}): void {
  _dispatchNotification(options, {
    title: '任务失败',
    duplicatePrefix: 'failed:',
    playSound: safePlayFailedSound,
    matchModes: ['all', 'failed_only'],
  })
}

