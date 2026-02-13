import { ref, watch } from 'vue'

const STORAGE_KEYS = {
  contextSummaryEnabled: 'nf:agent:ctx_summary_enabled',
  contextSummaryThreshold: 'nf:agent:ctx_summary_threshold',
  reactModeEnabled: 'nf:agent:react_mode_enabled',
  temperature: 'nf:agent:temperature',
  maxTokens: 'nf:agent:max_tokens',
  timeout: 'nf:agent:timeout',
} as const

const LEGACY_KEYS = {
  contextSummaryEnabled: 'nf:assistant:ctx_summary_enabled',
  contextSummaryThreshold: 'nf:assistant:ctx_summary_threshold',
  reactModeEnabled: 'nf:assistant:react_mode_enabled',
  temperature: 'nf:assistant:temperature',
  maxTokens: 'nf:assistant:max_tokens',
  timeout: 'nf:assistant:timeout',
} as const

const contextSummaryEnabled = ref(false)
const contextSummaryThreshold = ref<number | null>(4000)
const reactModeEnabled = ref(false)
const agentTemperature = ref<number | null>(0.6)
const agentMaxTokens = ref<number | null>(8192)
const agentTimeout = ref<number | null>(90)

let initialized = false

function readRaw(key: string): string | null {
  if (typeof window === 'undefined') return null
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

function readBoolean(primaryKey: string, legacyKey: string, fallback: boolean): boolean {
  const raw = readRaw(primaryKey) ?? readRaw(legacyKey)
  if (raw == null) return fallback
  return raw === '1' || raw === 'true'
}

function readNumber(primaryKey: string, legacyKey: string, fallback: number | null): number | null {
  const raw = readRaw(primaryKey) ?? readRaw(legacyKey)
  if (!raw) return fallback
  const parsed = Number(raw)
  if (Number.isNaN(parsed) || parsed <= 0) return fallback
  return parsed
}

function persistBoolean(primaryKey: string, legacyKey: string, value: boolean) {
  if (typeof window === 'undefined') return
  try {
    const serialized = value ? '1' : '0'
    window.localStorage.setItem(primaryKey, serialized)
    window.localStorage.setItem(legacyKey, serialized)
  } catch {
    /* noop */
  }
}

function persistNumber(primaryKey: string, legacyKey: string, value: number | null) {
  if (typeof window === 'undefined') return
  if (value == null || Number.isNaN(value)) return
  try {
    const serialized = String(value)
    window.localStorage.setItem(primaryKey, serialized)
    window.localStorage.setItem(legacyKey, serialized)
  } catch {
    /* noop */
  }
}

function ensureInitialized() {
  if (initialized) return
  initialized = true

  contextSummaryEnabled.value = readBoolean(
    STORAGE_KEYS.contextSummaryEnabled,
    LEGACY_KEYS.contextSummaryEnabled,
    false,
  )
  contextSummaryThreshold.value = readNumber(
    STORAGE_KEYS.contextSummaryThreshold,
    LEGACY_KEYS.contextSummaryThreshold,
    4000,
  )
  reactModeEnabled.value = readBoolean(
    STORAGE_KEYS.reactModeEnabled,
    LEGACY_KEYS.reactModeEnabled,
    false,
  )
  agentTemperature.value = readNumber(STORAGE_KEYS.temperature, LEGACY_KEYS.temperature, 0.6)
  agentMaxTokens.value = readNumber(STORAGE_KEYS.maxTokens, LEGACY_KEYS.maxTokens, 8192)
  agentTimeout.value = readNumber(STORAGE_KEYS.timeout, LEGACY_KEYS.timeout, 90)

  watch(contextSummaryEnabled, val => {
    persistBoolean(STORAGE_KEYS.contextSummaryEnabled, LEGACY_KEYS.contextSummaryEnabled, !!val)
  }, { immediate: true })

  watch(contextSummaryThreshold, val => {
    if (val && val > 0) {
      persistNumber(STORAGE_KEYS.contextSummaryThreshold, LEGACY_KEYS.contextSummaryThreshold, val)
    }
  }, { immediate: true })

  watch(reactModeEnabled, val => {
    persistBoolean(STORAGE_KEYS.reactModeEnabled, LEGACY_KEYS.reactModeEnabled, !!val)
  }, { immediate: true })

  watch(agentTemperature, val => {
    if (val != null && !Number.isNaN(val) && val > 0) {
      persistNumber(STORAGE_KEYS.temperature, LEGACY_KEYS.temperature, val)
    }
  }, { immediate: true })

  watch(agentMaxTokens, val => {
    if (val != null && !Number.isNaN(val) && val > 0) {
      persistNumber(STORAGE_KEYS.maxTokens, LEGACY_KEYS.maxTokens, val)
    }
  }, { immediate: true })

  watch(agentTimeout, val => {
    if (val != null && !Number.isNaN(val) && val > 0) {
      persistNumber(STORAGE_KEYS.timeout, LEGACY_KEYS.timeout, val)
    }
  }, { immediate: true })
}

export function useAgentPreferences() {
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

  function setAgentTemperature(val: number | null) {
    agentTemperature.value = val != null && !Number.isNaN(val) && val > 0 ? val : null
  }

  function setAgentMaxTokens(val: number | null) {
    agentMaxTokens.value = val != null && !Number.isNaN(val) && val > 0 ? val : null
  }

  function setAgentTimeout(val: number | null) {
    agentTimeout.value = val != null && !Number.isNaN(val) && val > 0 ? val : null
  }

  function resetAgentPreferences() {
    setContextSummaryEnabled(false)
    setContextSummaryThreshold(4000)
    setReactModeEnabled(false)
    setAgentTemperature(0.6)
    setAgentMaxTokens(8192)
    setAgentTimeout(90)
  }

  return {
    contextSummaryEnabled,
    contextSummaryThreshold,
    reactModeEnabled,
    agentTemperature,
    agentMaxTokens,
    agentTimeout,
    setContextSummaryEnabled,
    setContextSummaryThreshold,
    setReactModeEnabled,
    setAgentTemperature,
    setAgentMaxTokens,
    setAgentTimeout,
    resetAgentPreferences,

    // backward-compatible aliases
    assistantTemperature: agentTemperature,
    assistantMaxTokens: agentMaxTokens,
    assistantTimeout: agentTimeout,
    setAssistantTemperature: setAgentTemperature,
    setAssistantMaxTokens: setAgentMaxTokens,
    setAssistantTimeout: setAgentTimeout,
    resetAssistantPreferences: resetAgentPreferences,
  }
}

