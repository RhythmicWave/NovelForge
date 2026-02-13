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
}

export interface AgentStreamEvent {
  type?: string
  data?: Record<string, any>
}

