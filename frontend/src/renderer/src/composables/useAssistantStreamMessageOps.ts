import type { Ref } from 'vue'

import type { AssistantPanelMessage, AssistantToolResult } from '@renderer/types/assistantPanel'
import { applyAgentStreamEvent } from './agentChatEvents'

interface ApplyAssistantStreamChunkOptions {
  messages: Ref<AssistantPanelMessage[]>
  targetIdx: number
  chunk: string
  reasoningBucketsOpen: Ref<Record<string, boolean>>
  isReasoningBucketOpen: (key: string) => boolean
  scrollToBottom: () => void
  schedule?: (cb: () => void) => void
  onToolsExecuted?: (tools: AssistantToolResult[]) => void
}

function appendReasoningSegment(
  msg: AssistantPanelMessage,
  text: string,
  isDelta: boolean,
  targetIdx: number,
): string {
  const messageAny = msg as any
  if (!Array.isArray(messageAny.reasoningSegments)) {
    messageAny.reasoningSegments = msg.reasoning ? [msg.reasoning] : []
  }

  const allSegments: string[] = messageAny.reasoningSegments
  const hasGroups = Array.isArray(msg.toolGroups) && msg.toolGroups.length > 0

  if (!hasGroups) {
    if (!Array.isArray(messageAny.preToolReasoningSegments)) {
      messageAny.preToolReasoningSegments = []
    }
    const bucketSegments: string[] = messageAny.preToolReasoningSegments
    let segmentIndex: number

    if (isDelta && msg._lastAssistantEvent === 'reasoning' && bucketSegments.length > 0 && allSegments.length > 0) {
      segmentIndex = bucketSegments.length - 1
      bucketSegments[segmentIndex] = (bucketSegments[segmentIndex] || '') + text
      allSegments[allSegments.length - 1] = (allSegments[allSegments.length - 1] || '') + text
    } else {
      bucketSegments.push(text)
      allSegments.push(text)
      segmentIndex = bucketSegments.length - 1
    }

    return `plain-${targetIdx}-${segmentIndex}`
  }

  const groups = msg.toolGroups as any[]
  const groupIndex = groups.length - 1
  const lastGroup = groups[groupIndex]
  if (!Array.isArray(lastGroup.reasoningSegments)) {
    lastGroup.reasoningSegments = []
  }
  const bucketSegments: string[] = lastGroup.reasoningSegments
  let segmentIndex: number

  if (isDelta && msg._lastAssistantEvent === 'reasoning' && bucketSegments.length > 0 && allSegments.length > 0) {
    segmentIndex = bucketSegments.length - 1
    bucketSegments[segmentIndex] = (bucketSegments[segmentIndex] || '') + text
    allSegments[allSegments.length - 1] = (allSegments[allSegments.length - 1] || '') + text
  } else {
    bucketSegments.push(text)
    allSegments.push(text)
    segmentIndex = bucketSegments.length - 1
  }

  return `g-${targetIdx}-${groupIndex}-${segmentIndex}`
}

function mergeDuplicateReasoningSegments(msg: AssistantPanelMessage): void {
  const messageAny = msg as any
  const allSegments: string[] = messageAny.reasoningSegments || []
  if (allSegments.length <= 1) {
    return
  }

  const merged: string[] = []
  for (const segment of allSegments) {
    if (!merged.length || merged[merged.length - 1] !== segment) {
      merged.push(segment)
    }
  }

  if (merged.length !== allSegments.length) {
    allSegments.splice(0, allSegments.length, ...merged)
  }
}


export function applyAssistantStreamChunk(options: ApplyAssistantStreamChunkOptions): void {
  const schedule = options.schedule || ((cb: () => void) => cb())
  let event: any = null
  try {
    event = JSON.parse(options.chunk)
  } catch {
    event = null
  }

  if (event && typeof event === 'object' && event.type) {
    const type = event.type as string
    const data = (event.data || {}) as any

    const baseMessage = options.messages.value[options.targetIdx]
    if (!baseMessage) {
      console.warn(`[AssistantPanel] 目标消息索引 ${options.targetIdx} 不存在，忽略事件`, event)
      return
    }

    if (type !== 'reasoning' && baseMessage.role === 'assistant') {
      const messageAny = baseMessage as any
      const lastKey = messageAny._lastReasoningBucketKey as string | undefined
      if (lastKey && options.isReasoningBucketOpen(lastKey)) {
        options.reasoningBucketsOpen.value[lastKey] = false
      }
      messageAny._lastReasoningBucketKey = undefined
    }

    if (type === 'token') {
      const text = String(data.text || '')
      if (!text) return

      const msg = options.messages.value[options.targetIdx]
      applyAgentStreamEvent(msg as any, event as any, {
        trackToolStartInTools: false,
        appendErrorToContent: false,
        trackTimeline: true,
      })
      if (msg.role === 'assistant') {
        if (msg._hasReasoning && msg._showReasoning && !msg._reasoningUserToggled) {
          msg._showReasoning = false
        }

        if (!msg.toolCompleted) {
          msg.preToolText = (msg.preToolText || '') + text
        } else {
          if (!msg.toolGroups || msg.toolGroups.length === 0) {
            msg.toolGroups = [{ tools: [], postText: '' }]
          }
          const lastGroup = msg.toolGroups[msg.toolGroups.length - 1]
          lastGroup.postText = (lastGroup.postText || '') + text
        }

        msg._lastAssistantEvent = 'token'
      }

      if (msg.toolsInProgress && !msg.toolsInProgress.includes('❌')) {
        schedule(() => {
          const latest = options.messages.value[options.targetIdx]
          if (!latest) return
          latest.toolsInProgress = undefined
        })
      }

      options.scrollToBottom()
      return
    }

    if (type === 'tool_start') {
      applyAgentStreamEvent(baseMessage as any, event as any, {
        trackToolStartInTools: false,
        appendErrorToContent: false,
        trackTimeline: true,
      })
      options.scrollToBottom()
      return
    }

      if (type === 'tool_end') {
      const toolResult: AssistantToolResult = {
        tool_name: data.tool_name,
        result: data.result,
      }
      const msg = options.messages.value[options.targetIdx]
      applyAgentStreamEvent(msg as any, event as any, {
        trackToolStartInTools: false,
        appendErrorToContent: false,
        trackTimeline: true,
      })

      if (!msg.toolGroups) {
        msg.toolGroups = []
      }

      const lastEvent = msg._lastAssistantEvent
      if (!msg.toolGroups.length || lastEvent !== 'tool_end') {
        msg.toolGroups.push({ tools: [toolResult], postText: '' })
      } else {
        msg.toolGroups[msg.toolGroups.length - 1].tools.push(toolResult)
      }

      msg.toolsInProgress = undefined
      msg.toolCompleted = true
      msg._lastAssistantEvent = 'tool_end'

      options.onToolsExecuted?.([toolResult])
      options.scrollToBottom()
      return
    }

    if (type === 'tool_summary') {
      const tools = Array.isArray(data.tools) ? (data.tools as AssistantToolResult[]) : []
      if (tools.length) {
        options.onToolsExecuted?.(tools)
      }
      baseMessage.toolsInProgress = undefined
      options.scrollToBottom()
      return
    }

    if (type === 'reasoning') {
      const text = (data.text ?? '').toString()
      if (!text) return

      const msg = options.messages.value[options.targetIdx]
      if (msg.role === 'assistant') {
        applyAgentStreamEvent(msg as any, event as any, {
          trackToolStartInTools: false,
          appendErrorToContent: false,
          trackTimeline: true,
        })

        const isDelta = data.delta === true
        const bucketKey = appendReasoningSegment(msg, text, isDelta, options.targetIdx)

        mergeDuplicateReasoningSegments(msg)

        if (!isDelta && bucketKey) {
          options.reasoningBucketsOpen.value[bucketKey] = true
        }

        ;(msg as any)._lastReasoningBucketKey = bucketKey

        const allSegments: string[] = ((msg as any).reasoningSegments || []) as string[]
        msg.reasoning = allSegments.join('\n\n')
        msg._hasReasoning = true
        msg._lastAssistantEvent = 'reasoning'

        if (msg._showReasoning === undefined) {
          msg._showReasoning = true
        }
      }

      options.scrollToBottom()
      return
    }

    if (type === 'retry') {
      const reason = data.reason || '工具调用失败'
      const current = data.current ?? data.retry
      const max = data.max
      baseMessage.toolsInProgress = `🔄 工具调用失败，${reason}，正在重试 (${current}/${max})...`
      options.scrollToBottom()
      return
    }

    if (type === 'error') {
      const errMessage = data.error || '执行失败'
      applyAgentStreamEvent(baseMessage as any, event as any, {
        trackToolStartInTools: false,
        appendErrorToContent: false,
      })
      baseMessage.toolsInProgress = `❌ 工具调用失败: ${errMessage}`
      options.scrollToBottom()
      return
    }

    return
  }

  const plain = (options.chunk ?? '').toString()
  if (!plain) return

  const msg = options.messages.value[options.targetIdx]
  if (!msg) {
    console.warn(`⚠️ [AssistantPanel] 目标消息索引 ${options.targetIdx} 不存在，停止流式输出`)
    return
  }

  if (msg.role === 'assistant') {
    applyAgentStreamEvent(msg as any, {
      type: 'token',
      data: { text: plain },
    } as any, {
      trackToolStartInTools: false,
      appendErrorToContent: false,
      trackTimeline: true,
    })

    if (!msg.toolCompleted) {
      msg.preToolText = (msg.preToolText || '') + plain
    } else {
      msg.postToolText = (msg.postToolText || '') + plain
    }
    msg._lastAssistantEvent = 'token'
  } else {
    msg.content += plain
  }

  options.scrollToBottom()
}

export function resetAssistantMessageForRegenerate(message: AssistantPanelMessage): void {
  message.content = ''
  message.timeline = []
  message.preToolText = undefined
  message.postToolText = undefined
  message.toolCompleted = undefined
  message.tools = undefined
  message.toolGroups = undefined
  message.toolsInProgress = undefined
  message._lastAssistantEvent = undefined
  message.reasoning = undefined
  message.reasoningSegments = undefined
  message.preToolReasoningSegments = undefined
  message._showReasoning = undefined
  message._hasReasoning = false
  message._reasoningUserToggled = undefined
  message._lastReasoningBucketKey = undefined
}
