import { defineStore } from 'pinia'

export interface AIParamCard {
  id: string
  name: string
  description?: string
  llm_config_id?: number
  prompt_name?: string
  response_model_name?: string
  temperature?: number
  max_tokens?: number
}

export const useAIParamCardStore = defineStore('aiParamCard', {
  state: () => ({
    paramCards: [] as AIParamCard[]
  }),
  
  getters: {
    // 通用查找：支持使用 id 或 name 作为“key”来获取参数卡
    findByKey: (state) => {
      return (key?: string) => {
        if (!key) return undefined
        return state.paramCards.find(c => c.id === key || c.name === key)
      }
    }
  },
  
  actions: {
    loadFromLocal() {
      const saved = localStorage.getItem('ai-param-cards')
      if (saved) {
        this.paramCards = JSON.parse(saved)
      }
    },

    saveToLocal() {
      localStorage.setItem('ai-param-cards', JSON.stringify(this.paramCards))
    },

    addCard(card: AIParamCard) {
      this.paramCards.push(card)
      this.saveToLocal()
    },

    updateCard(index: number, card: AIParamCard) {
      // 确保数组变化能被响应式系统检测到
      this.paramCards.splice(index, 1, card)
      this.saveToLocal()
    },

    deleteCard(index: number) {
      this.paramCards.splice(index, 1)
      this.saveToLocal()
    }
  }
}) 