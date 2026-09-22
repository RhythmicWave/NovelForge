export interface AgentToolTrace {
  tool_name: string
  args?: any
  result?: any
}

export interface AgentTimelineItem {
  kind: 'reasoning' | 'text' | 'tool'
  text?: string
  tool?: AgentToolTrace
}

export interface AgentChatMessage {
  role: 'user' | 'assistant'
  content: string
  tools?: AgentToolTrace[]
  reasoning?: string
  toolsInProgress?: string
  timeline?: AgentTimelineItem[]
  /** 生成失败原因（连接错误/流中断等），用于渲染错误卡片与重试入口 */
  error?: string
}

export interface AgentStreamEvent {
  type?: string
  data?: Record<string, any>
}

