import type { Ref } from 'vue'

import type { AssistantPanelMessage } from '@renderer/types/assistantPanel'

interface AssistantInjectedRefLite {
  projectName: string
  cardTitle: string
  content: any
}

interface AssistantContextLite {
  active_card: {
    title: string
    card_id: number
    card_type: string
  } | null
}

interface AssistantStoreLite {
  projectStructure: any
  formatRecentOperations: () => string
  getContextForAssistant: () => AssistantContextLite
  injectedRefs: AssistantInjectedRefLite[]
}

interface AssistantPreferenceRefs {
  contextSummaryEnabled: Ref<boolean>
  contextSummaryThreshold: Ref<number | null>
  reactModeEnabled: Ref<boolean>
  assistantTemperature: Ref<number | null>
  assistantMaxTokens: Ref<number | null>
  assistantTimeout: Ref<number | null>
}

interface UseAssistantRequestBuilderOptions {
  messages: Ref<AssistantPanelMessage[]>
  assistantStore: AssistantStoreLite
  resolvedContext: Ref<string>
  effectiveSchema: Ref<any>
  preferences: AssistantPreferenceRefs
}

function pruneEmpty(val: any): any {
  if (val == null) return val
  if (typeof val === 'string') return val.trim() === '' ? undefined : val
  if (typeof val !== 'object') return val
  if (Array.isArray(val)) {
    return val.map(pruneEmpty).filter(item => item !== undefined)
  }
  const out: Record<string, any> = {}
  for (const [key, value] of Object.entries(val)) {
    const pruned = pruneEmpty(value)
    if (pruned === undefined) continue
    if (typeof pruned === 'object' && !Array.isArray(pruned) && Object.keys(pruned).length === 0) continue
    if (Array.isArray(pruned) && pruned.length === 0) continue
    out[key] = pruned
  }
  return out
}

export function useAssistantRequestBuilder(options: UseAssistantRequestBuilderOptions) {
  function buildConversationText() {
    return options.messages.value
      .map(message => {
        const prefix = message.role === 'user' ? 'User:' : 'Assistant:'
        let text = `${prefix} ${message.content}`
        if (message.tools && message.tools.length > 0) {
          text += '\n\n[工具调用记录]'
          for (const tool of message.tools) {
            text += `\n- 工具: ${tool.tool_name}`
            if (tool.result) {
              text += `\n  结果: ${JSON.stringify(tool.result, null, 2)}`
            }
          }
        }
        return text
      })
      .join('\n\n')
  }

  function buildAssistantChatRequest() {
    const parts: string[] = []
    const projectStructure = options.assistantStore.projectStructure

    if (projectStructure) {
      parts.push(`# 项目: ${projectStructure.project_name}`)
      parts.push(`项目ID: ${projectStructure.project_id} | 卡片总数: ${projectStructure.total_cards}`)
      parts.push('')

      const stats = Object.entries(projectStructure.stats)
        .map(([type, count]) => `- ${type}: ${count} 张`)
        .join('\n')
      parts.push(`## 📊 项目统计\n${stats}`)
      parts.push('')

      parts.push(`## 🌲 卡片结构树\nROOT\n${projectStructure.tree_text}`)
      parts.push('')

      parts.push('## 🏷️ 可用卡片类型')
      parts.push(projectStructure.available_card_types.join(' | '))
      parts.push('')
    }

    const opsText = options.assistantStore.formatRecentOperations()
    if (opsText) {
      parts.push(`## 📝 近期操作\n${opsText}`)
      parts.push('')
    }

    const context = options.assistantStore.getContextForAssistant()
    if (context.active_card) {
      parts.push('## ⭐ 当前卡片')
      parts.push(`"${context.active_card.title}" (ID: ${context.active_card.card_id}, 类型: ${context.active_card.card_type})`)

      if (options.effectiveSchema.value) {
        try {
          const schemaText = JSON.stringify(options.effectiveSchema.value, null, 2)
          parts.push('\n### 卡片结构 (JSON Schema)')
          parts.push('```json')
          parts.push(schemaText)
          parts.push('```')
        } catch {
          // ignore schema serialization error
        }
      }

      parts.push('')
    }

    if (options.assistantStore.injectedRefs.length) {
      const blocks: string[] = []
      for (const ref of options.assistantStore.injectedRefs) {
        try {
          const cleaned = pruneEmpty(ref.content)
          const text = JSON.stringify(cleaned ?? {}, null, 2)
          const clipped = text.length > 4000 ? `${text.slice(0, 4000)}\n/* ... */` : text
          blocks.push(`### 【引用】${ref.projectName} / ${ref.cardTitle}\n\`\`\`json\n${clipped}\n\`\`\``)
        } catch {
          // ignore serialization error for single ref
        }
      }
      parts.push(`## 📎 引用卡片\n${blocks.join('\n\n')}`)
      parts.push('')
    }

    if (options.resolvedContext.value) {
      parts.push(`## 🔗 上下文引用\n${options.resolvedContext.value}`)
      parts.push('')
    }

    parts.push('## 💬 对话历史')
    parts.push(buildConversationText())

    const lastUserMessage = options.messages.value.filter(message => message.role === 'user').pop()
    const userPrompt = lastUserMessage?.content?.trim() || ''

    return {
      user_prompt: userPrompt,
      context_info: parts.join('\n'),
      context_summarization_enabled: options.preferences.contextSummaryEnabled.value || undefined,
      context_summarization_threshold: options.preferences.contextSummaryThreshold.value || undefined,
      react_mode_enabled: options.preferences.reactModeEnabled.value || undefined,
      temperature: options.preferences.assistantTemperature.value || undefined,
      max_tokens: options.preferences.assistantMaxTokens.value || undefined,
      timeout: options.preferences.assistantTimeout.value || undefined,
    }
  }

  return {
    buildConversationText,
    buildAssistantChatRequest,
  }
}
