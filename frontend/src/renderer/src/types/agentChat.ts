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
  /** 本轮是否已经收到工具事件；断流后用于阻止无条件重放副作用请求 */
  toolExecutionStarted?: boolean
  /** 工具事件后流异常结束，执行结果可能未知 */
  executionUnknown?: boolean
  streamStatus?: 'running' | 'completed' | 'failed' | 'cancelled'
}

export interface AgentStreamEvent {
  type?: string
  data?: Record<string, any>
}

