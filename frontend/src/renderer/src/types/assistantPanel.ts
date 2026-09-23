import type { AgentTimelineItem } from '@renderer/types/agentChat'

export interface AssistantToolResult {
  tool_name: string
  args?: any
  result: any
}

export interface AssistantToolGroup {
  tools: AssistantToolResult[]
  postText: string
  reasoningSegments?: string[]
}

export interface AssistantPanelMessage {
  role: 'user' | 'assistant'
  content: string
  tools?: AssistantToolResult[]
  toolsInProgress?: string
  timeline?: AgentTimelineItem[]
  preToolText?: string
  postToolText?: string
  toolCompleted?: boolean
  toolGroups?: AssistantToolGroup[]
  _lastAssistantEvent?: 'token' | 'tool_end' | 'reasoning'
  reasoning?: string
  reasoningSegments?: string[]
  preToolReasoningSegments?: string[]
  _showReasoning?: boolean
  _hasReasoning?: boolean
  _reasoningUserToggled?: boolean
  _lastReasoningBucketKey?: string
  /** 生成失败原因（连接错误/流中断等），用于渲染错误卡片与重试入口 */
  error?: string
  /** 本轮是否已经收到工具事件；断流后用于阻止无条件重放副作用请求 */
  toolExecutionStarted?: boolean
  /** 工具事件后流异常结束，执行结果可能未知 */
  executionUnknown?: boolean
  streamStatus?: 'running' | 'completed' | 'failed' | 'cancelled'
}

export interface AssistantChatSession {
  id: string
  projectId: number
  title: string
  createdAt: number
  updatedAt: number
  messages: AssistantPanelMessage[]
}
