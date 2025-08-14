import { defineStore } from 'pinia'

export interface ConsistencySettings {
  kg_enabled: boolean
  consistency_mode: 'off' | 'light' | 'strict'
  kg_trigger: {
    on_chapter_window_close: { enabled: boolean; window_size: number }
    on_outline_change: { enabled: boolean; sensitive_fields: string[] }
    cron: { enabled: boolean; expr: string }
    manual: { enabled: boolean }
  }
  kg_features: {
    aliases: boolean
    state_snapshots: boolean
    relations: 'none' | 'basic' | 'full'
  }
  kg_cost_budget: {
    llm_calls_per_build: number
    use_embedding: boolean
    use_reranker: boolean
  }
}

const DEFAULT_SETTINGS: ConsistencySettings = {
  kg_enabled: true,
  consistency_mode: 'light',
  kg_trigger: {
    on_chapter_window_close: { enabled: true, window_size: 3 },
    on_outline_change: { enabled: true, sensitive_fields: ['character_level_and_wealth_changes', 'character_list'] },
    cron: { enabled: false, expr: '0 3 * * *' },
    manual: { enabled: true }
  },
  kg_features: {
    aliases: true,
    state_snapshots: true,
    relations: 'basic'
  },
  kg_cost_budget: {
    llm_calls_per_build: 1,
    use_embedding: false,
    use_reranker: false
  }
}

export const useConsistencySettingsStore = defineStore('consistencySettings', {
  state: () => ({
    settings: { ...DEFAULT_SETTINGS } as ConsistencySettings
  }),
  actions: {
    loadFromLocal() {
      const raw = localStorage.getItem('consistency-settings')
      if (raw) {
        try {
          const obj = JSON.parse(raw)
          // 做一次浅合并，保证新增字段有默认值
          this.settings = { ...DEFAULT_SETTINGS, ...obj,
            kg_trigger: { ...DEFAULT_SETTINGS.kg_trigger, ...(obj?.kg_trigger || {}) },
            kg_features: { ...DEFAULT_SETTINGS.kg_features, ...(obj?.kg_features || {}) },
            kg_cost_budget: { ...DEFAULT_SETTINGS.kg_cost_budget, ...(obj?.kg_cost_budget || {}) }
          }
        } catch {
          this.settings = { ...DEFAULT_SETTINGS }
        }
      } else {
        this.settings = { ...DEFAULT_SETTINGS }
      }
    },
    saveToLocal() {
      localStorage.setItem('consistency-settings', JSON.stringify(this.settings))
    },
    resetToDefault() {
      this.settings = { ...DEFAULT_SETTINGS }
      this.saveToLocal()
    }
  }
}) 