import { ref, watch } from 'vue'

const STORAGE_KEYS = {
  contextSummaryEnabled: 'nf:assistant:ctx_summary_enabled',
  contextSummaryThreshold: 'nf:assistant:ctx_summary_threshold',
  reactModeEnabled: 'nf:assistant:react_mode_enabled'
} as const

const contextSummaryEnabled = ref(false)
const contextSummaryThreshold = ref<number | null>(4000)
const reactModeEnabled = ref(false)

let initialized = false

function readBoolean(key: string, fallback: boolean): boolean {
  if (typeof window === 'undefined') return fallback
  try {
    const raw = window.localStorage.getItem(key)
    if (raw === null) return fallback
    return raw === '1' || raw === 'true'
  } catch {
    return fallback
  }
}

function readNumber(key: string, fallback: number | null): number | null {
  if (typeof window === 'undefined') return fallback
  try {
    const raw = window.localStorage.getItem(key)
    if (!raw) return fallback
    const parsed = Number(raw)
    if (Number.isNaN(parsed) || parsed <= 0) return fallback
    return parsed
  } catch {
    return fallback
  }
}

function persistBoolean(key: string, value: boolean) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(key, value ? '1' : '0')
  } catch {
    /* noop */
  }
}

function persistNumber(key: string, value: number | null) {
  if (typeof window === 'undefined') return
  if (value == null || Number.isNaN(value)) return
  try {
    window.localStorage.setItem(key, String(value))
  } catch {
    /* noop */
  }
}

function ensureInitialized() {
  if (initialized) return
  initialized = true

  contextSummaryEnabled.value = readBoolean(STORAGE_KEYS.contextSummaryEnabled, false)
  contextSummaryThreshold.value = readNumber(STORAGE_KEYS.contextSummaryThreshold, 4000)
  reactModeEnabled.value = readBoolean(STORAGE_KEYS.reactModeEnabled, false)

  watch(contextSummaryEnabled, (val) => persistBoolean(STORAGE_KEYS.contextSummaryEnabled, !!val), { immediate: true })
  watch(contextSummaryThreshold, (val) => {
    if (val && val > 0) persistNumber(STORAGE_KEYS.contextSummaryThreshold, val)
  }, { immediate: true })
  watch(reactModeEnabled, (val) => persistBoolean(STORAGE_KEYS.reactModeEnabled, !!val), { immediate: true })
}

export function useAssistantPreferences() {
  ensureInitialized()

  function setContextSummaryEnabled(val: boolean) {
    contextSummaryEnabled.value = !!val
  }

  function setContextSummaryThreshold(val: number | null) {
    contextSummaryThreshold.value = val && val > 0 ? val : null
  }

  function setReactModeEnabled(val: boolean) {
    reactModeEnabled.value = !!val
  }

  function resetAssistantPreferences() {
    setContextSummaryEnabled(false)
    setContextSummaryThreshold(4000)
    setReactModeEnabled(false)
  }

  return {
    contextSummaryEnabled,
    contextSummaryThreshold,
    reactModeEnabled,
    setContextSummaryEnabled,
    setContextSummaryThreshold,
    setReactModeEnabled,
    resetAssistantPreferences
  }
}
