import { defineStore } from 'pinia'

export interface PerCardAIParams {
  llm_config_id?: number
  prompt_name?: string
  response_model_name?: string
  temperature?: number
  max_tokens?: number
  timeout?: number
}

export const usePerCardAISettingsStore = defineStore('perCardAISettings', {
  state: () => ({
    byCardId: {} as Record<string | number, PerCardAIParams>
  }),

  getters: {
    getByCardId: (state) => {
      return (cardId: string | number | undefined) => {
        if (cardId == null) return undefined
        return state.byCardId[String(cardId)]
      }
    }
  },

  actions: {
    loadFromLocal() {
      try {
        const s = localStorage.getItem('per-card-ai-settings')
        if (s) this.byCardId = JSON.parse(s)
      } catch {}
    },
    saveToLocal() {
      try { localStorage.setItem('per-card-ai-settings', JSON.stringify(this.byCardId)) } catch {}
    },
    setForCard(cardId: string | number, params: PerCardAIParams) {
      this.byCardId[String(cardId)] = { ...(this.byCardId[String(cardId)] || {}), ...params }
      this.saveToLocal()
    },
    removeForCard(cardId: string | number) {
      delete this.byCardId[String(cardId)]
      this.saveToLocal()
    }
  }
}) 