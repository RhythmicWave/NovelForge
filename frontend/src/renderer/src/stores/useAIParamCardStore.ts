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
  built_in?: boolean
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
      } else {
        // 首次初始化：根据提供的清单注入系统预设参数卡
        this.paramCards = [
          {"name":"金手指生成","id":"card-001","prompt_name":"task0","description":"专门用于生成金手指的配置","llm_config_id":1,"response_model_name":"Task0Response","temperature":0.7,"max_tokens":1024, built_in: true},
          {"name":"一句话梗概生成","id":"card-002","prompt_name":"task1","description":"专门用于生成一句话梗概的配置","llm_config_id":1,"response_model_name":"Task1Response","temperature":0.7,"max_tokens":512, built_in: true},
          {"name":"大纲扩写生成","id":"card-003","prompt_name":"task2","description":"专门用于生成大纲扩写的配置","llm_config_id":1,"response_model_name":"Task2Response","temperature":0.7,"max_tokens":2048, built_in: true},
          {"name":"世界观生成","id":"card-004","prompt_name":"task3","description":"专门用于生成世界观的配置","llm_config_id":1,"response_model_name":"WorldBuildingResponse","temperature":0.7,"max_tokens":2048, built_in: true},
          {"name":"蓝图生成","id":"card-005","prompt_name":"task4","description":"生成角色和场景蓝图","llm_config_id":1,"response_model_name":"BlueprintResponse","temperature":0.7,"max_tokens":2048, built_in: true},
          {"name":"分卷大纲生成","id":"card-006","prompt_name":"task5","description":"生成分卷大纲","llm_config_id":1,"response_model_name":"VolumeOutlineResponse","temperature":0.7,"max_tokens":2048, built_in: true},
          {"name":"章节大纲生成","id":"card-007","prompt_name":"task6","description":"专门用于生成章节大纲的配置","llm_config_id":2,"response_model_name":"ChapterOutlineResponse","temperature":0.7,"max_tokens":2048, built_in: true},
          {"name":"通用生成","id":"card-008","prompt_name":"task0","description":"适用于大多数AI生成任务的通用配置","llm_config_id":2,"response_model_name":"","temperature":0.7,"max_tokens":1500, built_in: true},
          {"name":"test","id":"card-1754723140469","prompt_name":"test","description":"","llm_config_id":2,"response_model_name":"test","temperature":0.7,"max_tokens":2000}
        ]
        this.saveToLocal()
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