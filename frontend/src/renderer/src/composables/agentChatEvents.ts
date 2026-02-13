import type { AgentChatMessage, AgentStreamEvent, AgentTimelineItem, AgentToolTrace } from '@/types/agentChat'

interface ApplyAgentEventOptions {
  onToolEnd?: (toolName: string, result: any) => void
  trackToolStartInTools?: boolean
  appendErrorToContent?: boolean
  trackTimeline?: boolean
}

interface SanitizedTokenParts {
  visibleText: string
  reasoningText: string
}

function ensureTimeline(target: AgentChatMessage): AgentTimelineItem[] {
  if (!Array.isArray(target.timeline)) {
    target.timeline = []
  }
  return target.timeline
}

function appendTextTimeline(target: AgentChatMessage, text: string) {
  if (!text) return
  const timeline = ensureTimeline(target)
  const last = timeline[timeline.length - 1]
  if (last?.kind === 'text') {
    last.text = `${last.text || ''}${text}`
    return
  }

  if (!text.trim()) {
    return
  }

  timeline.push({ kind: 'text', text })
}

function appendReasoningTimeline(target: AgentChatMessage, text: string, isDelta: boolean) {
  const normalized = (text || '').trim()
  if (!normalized) return
  const timeline = ensureTimeline(target)
  const last = timeline[timeline.length - 1]

  if (!isDelta) {
    const duplicated = timeline.some(item => item.kind === 'reasoning' && (item.text || '').trim() === normalized)
    if (duplicated) {
      return
    }
  }

  if (last?.kind === 'reasoning') {
    const lastNormalized = (last.text || '').trim()
    if (isDelta) {
      last.text = `${last.text || ''}${text}`
      return
    }

    if (normalized.startsWith(lastNormalized) && normalized !== lastNormalized) {
      last.text = text
      return
    }

    if (lastNormalized.startsWith(normalized)) {
      return
    }

    if (lastNormalized === normalized) {
      return
    }
  }

  timeline.push({ kind: 'reasoning', text })
}

function appendToolTimeline(target: AgentChatMessage, tool: AgentToolTrace) {
  const timeline = ensureTimeline(target)
  timeline.push({ kind: 'tool', tool })
}

function stripThinkTags(rawText: string): SanitizedTokenParts {
  if (!rawText) return { visibleText: '', reasoningText: '' }

  let working = rawText
  const reasoningParts: string[] = []

  const blockPattern = /<think>([\s\S]*?)<\/think>/gi
  working = working.replace(blockPattern, (_, inner: string) => {
    const normalized = (inner || '').trim()
    if (normalized) {
      reasoningParts.push(normalized)
    }
    return ''
  })

  working = working
    .replace(/<\/?think>/gi, '')
    .replace(/<\/?thinking>/gi, '')

  return {
    visibleText: working,
    reasoningText: reasoningParts.join('\n\n'),
  }
}

export function ensureAssistantMessage(messages: AgentChatMessage[]): AgentChatMessage {
  const last = messages[messages.length - 1]
  if (last && last.role === 'assistant') {
    return last
  }
  const message: AgentChatMessage = { role: 'assistant', content: '', tools: [], timeline: [] }
  messages.push(message)
  return message
}

export function applyAgentStreamEvent(
  target: AgentChatMessage,
  event: AgentStreamEvent,
  options?: ApplyAgentEventOptions,
): void {
  const type = event?.type
  const data = event?.data || {}

  if (type === 'token') {
    const text = String(data.text || '')
    const { visibleText, reasoningText } = stripThinkTags(text)

    ;(target as any)._agentLastEventType = visibleText.trim() ? 'token' : (reasoningText ? 'reasoning' : 'token')

    if (reasoningText) {
      target.reasoning = (target.reasoning || '') + reasoningText
      if (options?.trackTimeline) {
        appendReasoningTimeline(target, reasoningText, false)
      }
    }

    if (visibleText) {
      target.content += visibleText
      if (options?.trackTimeline) {
        appendTextTimeline(target, visibleText)
      }
    }
    return
  }

  if (type === 'reasoning') {
    const text = String(data.text || '')
    const normalized = text.trim()
    if (!normalized) {
      return
    }

    ;(target as any)._agentLastEventType = 'reasoning'

    target.reasoning = (target.reasoning || '') + text
    if (options?.trackTimeline) {
      appendReasoningTimeline(target, text, data.delta === true)
    }
    return
  }

  if (type === 'tool_start') {
    ;(target as any)._agentLastEventType = 'tool_start'
    if (options?.trackToolStartInTools !== false) {
      target.tools = target.tools || []
      target.tools.push({ tool_name: data.tool_name || 'tool', args: data.args })
    }
    target.toolsInProgress = `⏳ 正在调用工具: ${data.tool_name || '工具'}...`
    return
  }

  if (type === 'tool_end') {
    ;(target as any)._agentLastEventType = 'tool_end'
    target.tools = target.tools || []
    const toolName = data.tool_name || 'tool'
    const allowPendingMerge = options?.trackToolStartInTools !== false
    const reversed = allowPendingMerge ? [...target.tools].reverse() : []
    const pending = allowPendingMerge
      ? reversed.find(item => item.tool_name === toolName && item.result === undefined)
      : undefined

    if (pending) {
      pending.result = data.result
      if (pending.args === undefined && data.args !== undefined) {
        pending.args = data.args
      }
    } else {
      target.tools.push({ tool_name: toolName, args: data.args, result: data.result })
    }

    if (options?.trackTimeline) {
      appendToolTimeline(target, { tool_name: toolName, args: data.args, result: data.result })
    }

    target.toolsInProgress = undefined

    options?.onToolEnd?.(toolName, data.result)
    return
  }

  if (type === 'error') {
    ;(target as any)._agentLastEventType = 'error'
    target.toolsInProgress = undefined
    if (options?.appendErrorToContent !== false) {
      target.content += `\n\n[错误] ${data.error || 'unknown error'}`
    }
  }
}
