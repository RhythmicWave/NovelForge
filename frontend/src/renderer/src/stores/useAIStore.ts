import { defineStore } from 'pinia'
import { ref } from 'vue'
import { generateAIContent } from '@renderer/api/ai'
import { useCardStore } from './useCardStore'
import { showInterruptOverlay, hideInterruptOverlay } from '@renderer/services/interruptOverlay'

export const useAIStore = defineStore('ai', () => {
  const isGenerating = ref(false)
  const lastResult = ref<any>(null)
  let currentAbort: AbortController | null = null

  async function generateContent(
    responseModelName: string,
    inputText: string,
    llmConfigId: number,
    promptName?: string,
    sampling?: { temperature?: number; max_tokens?: number; timeout?: number }
  ) {
    if (isGenerating.value) return null
    isGenerating.value = true
    try {
      currentAbort?.abort()
      currentAbort = new AbortController()
      showInterruptOverlay('AI生成中…', () => { try { currentAbort?.abort() } catch {} })
      const cardStore = useCardStore()
      const allowed = new Set(['角色卡','场景卡','组织卡','物品卡','概念卡'])
      const typeIdToName = new Map<number, string>()
      ;(cardStore.cardTypes || []).forEach((t:any) => { if (t?.id) typeIdToName.set(t.id, (t as any).name || '') })
      const names = Array.from(new Set((cardStore.cards || []).map((c:any) => {
        const tname = typeIdToName.get(c.card_type_id) || ''
        if (!allowed.has(tname)) return null
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
      if (sampling) {
        if (typeof sampling.temperature === 'number') payload.temperature = sampling.temperature
        if (typeof sampling.max_tokens === 'number') payload.max_tokens = sampling.max_tokens
        if (typeof sampling.timeout === 'number') payload.timeout = sampling.timeout
      }
      const res = await generateAIContent(payload, { signal: currentAbort.signal })
      lastResult.value = (res as any)?.data ?? res
      return lastResult.value
    } finally {
      isGenerating.value = false
      currentAbort = null
      hideInterruptOverlay()
    }
  }

  async function generateContentWithSchema(
    responseModelSchema: any,
    inputText: string,
    llmConfigId: number,
    promptName?: string,
    sampling?: { temperature?: number; max_tokens?: number; timeout?: number }
  ) {
    if (isGenerating.value) return null
    isGenerating.value = true
    try {
      currentAbort?.abort()
      currentAbort = new AbortController()
      showInterruptOverlay('AI生成中…', () => { try { currentAbort?.abort() } catch {} })
      const cardStore = useCardStore()
      const allowed = new Set(['角色卡','场景卡','组织卡','物品卡','概念卡'])
      const typeIdToName = new Map<number, string>()
      ;(cardStore.cardTypes || []).forEach((t:any) => { if (t?.id) typeIdToName.set(t.id, (t as any).name || '') })
      const names = Array.from(new Set((cardStore.cards || []).map((c:any) => {
        const tname = typeIdToName.get(c.card_type_id) || ''
        if (!allowed.has(tname)) return null
        const nm = (c?.content?.name || '').trim()
        return nm || null
      }).filter(Boolean))) as string[]
      const deps = JSON.stringify({ all_entity_names: names })

      const payload: any = {
        input: { input_text: inputText },
        llm_config_id: llmConfigId,
        prompt_name: promptName,
        response_model_schema: responseModelSchema,
        deps,
      }
      if (sampling) {
        if (typeof sampling.temperature === 'number') payload.temperature = sampling.temperature
        if (typeof sampling.max_tokens === 'number') payload.max_tokens = sampling.max_tokens
        if (typeof sampling.timeout === 'number') payload.timeout = sampling.timeout
      }
      const res = await generateAIContent(payload, { signal: currentAbort.signal })
      lastResult.value = (res as any)?.data ?? res
      return lastResult.value
    } finally {
      isGenerating.value = false
      currentAbort = null
      hideInterruptOverlay()
    }
  }

  function cancelGeneration() {
    try { currentAbort?.abort() } catch {}
    hideInterruptOverlay()
  }

  return { isGenerating, lastResult, generateContent, generateContentWithSchema, cancelGeneration }
}) 
