export type DesktopNotificationPermission = NotificationPermission | 'unsupported'
export type TaskDoneNotificationPermission = DesktopNotificationPermission

export type TaskDoneNotifyOptions = {
  taskId?: string
  title?: string
  body?: string
  enableSound?: boolean
  enableDesktopNotification?: boolean
  soundEnabled?: boolean
  desktopNotificationEnabled?: boolean
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

export async function warmupDoneSound(): Promise<boolean> {
  const AudioContextClass = getAudioContextConstructor()
  if (!AudioContextClass) return false

  let audioContext: AudioContext | undefined

  try {
    audioContext = new AudioContextClass()

    if (audioContext.state === 'suspended') {
      await audioContext.resume()
    }

    return audioContext.state !== 'suspended'
  } catch {
    return false
  } finally {
    if (audioContext) {
      audioContext.close().catch(() => {
        /* noop */
      })
    }
  }
}

export async function unlockTaskDoneSound(): Promise<boolean> {
  return warmupDoneSound()
}

function closeAudioContext(audioContext: AudioContext | undefined): void {
  if (!audioContext) return

  audioContext.close().catch(() => {
    /* noop */
  })
}

function scheduleTone(
  audioContext: AudioContext,
  frequency: number,
  startAt: number,
  duration: number
): void {
  const oscillator = audioContext.createOscillator()
  const gain = audioContext.createGain()

  oscillator.type = 'sine'
  oscillator.frequency.setValueAtTime(frequency, startAt)

  gain.gain.setValueAtTime(0.0001, startAt)
  gain.gain.exponentialRampToValueAtTime(0.8, startAt + 0.018)
  gain.gain.exponentialRampToValueAtTime(0.0001, startAt + duration)

  oscillator.connect(gain)
  gain.connect(audioContext.destination)
  oscillator.start(startAt)
  oscillator.stop(startAt + duration + 0.02)
}

function safePlayDoneSound(): boolean {
  const AudioContextClass = getAudioContextConstructor()
  if (!AudioContextClass) return false

  let audioContext: AudioContext | undefined

  const playBeep = (): boolean => {
    if (!audioContext) return false

    try {
      const now = audioContext.currentTime
      scheduleTone(audioContext, 880, now, 0.18)
      scheduleTone(audioContext, 1175, now + 0.2, 0.2)

      window.setTimeout(() => {
        closeAudioContext(audioContext)
        audioContext = undefined
      }, 450)
      return true
    } catch {
      closeAudioContext(audioContext)
      audioContext = undefined
      return false
    }
  }

  try {
    audioContext = new AudioContextClass()

    if (audioContext.state === 'suspended') {
      audioContext
        .resume()
        .then(() => {
          if (audioContext?.state !== 'suspended') playBeep()
          else closeAudioContext(audioContext)
        })
        .catch(() => {
          closeAudioContext(audioContext)
          audioContext = undefined
        })
      return true
    }

    return playBeep()
  } catch {
    closeAudioContext(audioContext)
    return false
  }
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

export function notifyTaskDone(options: TaskDoneNotifyOptions = {}): void {
  try {
    const {
      taskId,
      title = '任务已完成',
      body,
      enableSound,
      enableDesktopNotification,
      soundEnabled,
      desktopNotificationEnabled
    } = options

    const duplicateKey = taskId || `${title}\n${body || ''}`
    if (isDuplicateTaskDone(duplicateKey)) return

    if (enableSound ?? soundEnabled ?? false) {
      safePlayDoneSound()
    }

    if (enableDesktopNotification ?? desktopNotificationEnabled ?? false) {
      safeShowDesktopNotification(title, body)
    }
  } catch {
    /* noop */
  }
}
