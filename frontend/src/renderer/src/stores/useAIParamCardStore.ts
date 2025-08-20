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
  timeout?: number
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
        // 首次初始化：根据提供的清单注入系统预设参数卡（默认超时60秒）
        this.paramCards = [
          {"name":"金手指生成","id":"card-001","prompt_name":"金手指生成","description":"专门用于生成金手指的配置","llm_config_id":1,"response_model_name":"SpecialAbilityResponse","temperature":0.6,"max_tokens":1024, timeout: 60, built_in: true},
          {"name":"一句话梗概生成","id":"card-002","prompt_name":"一句话梗概","description":"专门用于生成一句话梗概的配置","llm_config_id":1,"response_model_name":"OneSentence","temperature":0.6,"max_tokens":1024, timeout: 60, built_in: true},
          {"name":"大纲扩写生成","id":"card-003","prompt_name":"一段话大纲","description":"专门用于生成大纲扩写的配置","llm_config_id":1,"response_model_name":"ParagraphOverview","temperature":0.6,"max_tokens":2048, timeout: 60, built_in: true},
          {"name":"世界观生成","id":"card-004","prompt_name":"世界观设定","description":"专门用于生成世界观的配置","llm_config_id":1,"response_model_name":"WorldBuilding","temperature":0.6,"max_tokens":8192, timeout: 120, built_in: true},
          {"name":"蓝图生成","id":"card-005","prompt_name":"核心蓝图","description":"生成角色和场景蓝图","llm_config_id":1,"response_model_name":"Blueprint","temperature":0.6,"max_tokens":8192, timeout: 120, built_in: true},
          {"name":"分卷大纲生成","id":"card-006","prompt_name":"分卷大纲","description":"生成分卷大纲","llm_config_id":1,"response_model_name":"VolumeOutline","temperature":0.6,"max_tokens":8192, timeout: 120, built_in: true},
          {"name":"阶段大纲生成","id":"card-007","prompt_name":"阶段大纲","description":"生成阶段大纲","llm_config_id":1,"response_model_name":"StageLine","temperature":0.6,"max_tokens":8192, timeout: 120, built_in: true},
          {"name":"章节大纲生成","id":"card-008","prompt_name":"章节大纲","description":"专门用于生成章节大纲的配置","llm_config_id":1,"response_model_name":"ChapterOutline","temperature":0.6,"max_tokens":4096, timeout: 60, built_in: true},
          {"name":"通用生成","id":"card-009","prompt_name":"内容生成","description":"适用于AI生成章节正文","llm_config_id":1,"response_model_name":"","temperature":0.7,"max_tokens":8192, timeout: 60, built_in: true},
          {"name":"写作指南","id":"card-010","prompt_name":"写作指南","description":"适用于AI生成章节正文","llm_config_id":1,"response_model_name":"WritingGuide","temperature":0.7,"max_tokens":8192, timeout: 60, built_in: true},
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