import { defineStore } from 'pinia'
import { ref } from 'vue'
import { generateAIContent } from '@renderer/api/ai'
import { useCardStore } from './useCardStore'

export const useAIStore = defineStore('ai', () => {
  const isGenerating = ref(false)
  const lastResult = ref<any>(null)

  async function generateContent(responseModelName: string, inputText: string, llmConfigId: number, promptName?: string) {
    if (isGenerating.value) return null
    isGenerating.value = true
    try {
      // 收集实体名称：仅继承自 Entity 的卡片（通过 output_model_name 判断）
      const cardStore = useCardStore()
      const allowed = new Set(['CharacterCard','SceneCard','OrganizationCard','ItemCard','ConceptCard'])
      const typeIdToModel = new Map<number, string>()
      ;(cardStore.cardTypes || []).forEach((t:any) => { if (t?.id) typeIdToModel.set(t.id, (t as any).output_model_name || '') })
      const names = Array.from(new Set((cardStore.cards || []).map((c:any) => {
        const om = typeIdToModel.get(c.card_type_id) || ''
        if (!allowed.has(om)) return null
        const nm = (c?.content?.name || '').trim()
        return nm || null
      }).filter(Boolean))) as string[]
      const deps = JSON.stringify({ all_entity_names: names })

      const payload: any = {
        input: { input_text: inputText },
        llm_config_id: llmConfigId,
        prompt_name: promptName,
        response_model_name: responseModelName,
        deps,
      }
      const res = await generateAIContent(payload)
      lastResult.value = (res as any)?.data ?? res
      return lastResult.value
    } finally {
      isGenerating.value = false
    }
  }

  return { isGenerating, lastResult, generateContent }
}) 