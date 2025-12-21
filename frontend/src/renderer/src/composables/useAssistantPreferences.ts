import { ref, watch } from 'vue'

const STORAGE_KEYS = {
  contextSummaryEnabled: 'nf:assistant:ctx_summary_enabled',
  contextSummaryThreshold: 'nf:assistant:ctx_summary_threshold',
  reactModeEnabled: 'nf:assistant:react_mode_enabled',
  assistantTemperature: 'nf:assistant:temperature',
  assistantMaxTokens: 'nf:assistant:max_tokens',
  assistantTimeout: 'nf:assistant:timeout',
} as const

const contextSummaryEnabled = ref(false)
const contextSummaryThreshold = ref<number | null>(4000)
const reactModeEnabled = ref(false)
// 灵感助手参数默认值
const assistantTemperature = ref<number | null>(0.6)
const assistantMaxTokens = ref<number | null>(8192)
const assistantTimeout = ref<number | null>(90)

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
  assistantTemperature.value = readNumber(STORAGE_KEYS.assistantTemperature, 0.6)
  assistantMaxTokens.value = readNumber(STORAGE_KEYS.assistantMaxTokens, 8192)
  assistantTimeout.value = readNumber(STORAGE_KEYS.assistantTimeout, 90)

  watch(contextSummaryEnabled, (val) => persistBoolean(STORAGE_KEYS.contextSummaryEnabled, !!val), { immediate: true })
  watch(contextSummaryThreshold, (val) => {
    if (val && val > 0) persistNumber(STORAGE_KEYS.contextSummaryThreshold, val)
  }, { immediate: true })
  watch(reactModeEnabled, (val) => persistBoolean(STORAGE_KEYS.reactModeEnabled, !!val), { immediate: true })
  watch(assistantTemperature, (val) => {
    if (val != null && !Number.isNaN(val) && val > 0) persistNumber(STORAGE_KEYS.assistantTemperature, val)
  }, { immediate: true })
  watch(assistantMaxTokens, (val) => {
    if (val != null && !Number.isNaN(val) && val > 0) persistNumber(STORAGE_KEYS.assistantMaxTokens, val)
  }, { immediate: true })
  watch(assistantTimeout, (val) => {
    if (val != null && !Number.isNaN(val) && val > 0) persistNumber(STORAGE_KEYS.assistantTimeout, val)
  }, { immediate: true })
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

  function setAssistantTemperature(val: number | null) {
    assistantTemperature.value = val != null && !Number.isNaN(val) && val > 0 ? val : null
  }

  function setAssistantMaxTokens(val: number | null) {
    assistantMaxTokens.value = val != null && !Number.isNaN(val) && val > 0 ? val : null
  }

  function setAssistantTimeout(val: number | null) {
    assistantTimeout.value = val != null && !Number.isNaN(val) && val > 0 ? val : null
  }

  function resetAssistantPreferences() {
    setContextSummaryEnabled(false)
    setContextSummaryThreshold(4000)
    setReactModeEnabled(false)
    setAssistantTemperature(0.6)
    setAssistantMaxTokens(8192)
    setAssistantTimeout(90)
  }

  return {
    contextSummaryEnabled,
    contextSummaryThreshold,
    reactModeEnabled,
    assistantTemperature,
    assistantMaxTokens,
    assistantTimeout,
    setContextSummaryEnabled,
    setContextSummaryThreshold,
    setReactModeEnabled,
    setAssistantTemperature,
    setAssistantMaxTokens,
    setAssistantTimeout,
    resetAssistantPreferences
  }
}
