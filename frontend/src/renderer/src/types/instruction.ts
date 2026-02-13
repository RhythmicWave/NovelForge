/**
 * 指令流生成相关的类型定义
 * 
 * 与后端的 Pydantic 模型保持一致
 */

// ==================== 指令格式定义 ====================

/**
 * 指令操作类型
 */
export type InstructionOp = 'set' | 'append' | 'done'

/**
 * 基础指令接口
 */
export interface InstructionBase {
  op: InstructionOp
}

/**
 * 设置字段值指令
 */
export interface SetInstruction extends InstructionBase {
  op: 'set'
  path: string  // JSON Pointer 格式，如 /name 或 /config/theme
  value: any    // 要设置的值
}

/**
 * 向数组追加元素指令
 */
export interface AppendInstruction extends InstructionBase {
  op: 'append'
  path: string  // JSON Pointer 格式的数组路径
  value: any    // 要追加的元素
}

/**
 * 生成完成标志指令
 */
export interface DoneInstruction extends InstructionBase {
  op: 'done'
}

/**
 * 指令联合类型
 */
export type Instruction = SetInstruction | AppendInstruction | DoneInstruction

// ==================== 生成配置 ====================

/**
 * 卡片生成配置
 */
export interface GenerationConfig {
  mode?: 'instruction_stream'
  prompt_template?: string
  field_hints?: Record<string, string>
  field_order?: string[]
  custom?: Record<string, any>
}

// ==================== API 请求/响应模型 ====================

/**
 * 对话消息
 */
export interface ConversationMessage {
  role: 'system' | 'user' | 'assistant'
  content: string
}

/**
 * 指令流生成请求
 */
export interface InstructionGenerateRequest {
  llm_config_id: number
  user_prompt?: string
  response_model_schema: Record<string, any>
  current_data?: Record<string, any>
  conversation_context?: ConversationMessage[]
  generation_config?: GenerationConfig
  prompt_template?: string
  context_info?: string
  temperature?: number
  max_tokens?: number
  timeout?: number
  deps?: string
}

// ==================== SSE 事件类型 ====================

/**
 * 思考事件（AI 的自然语言输出）
 */
export interface ThinkingEvent {
  type: 'thinking'
  text: string
}

/**
 * 指令事件（已校验的指令）
 */
export interface InstructionEvent {
  type: 'instruction'
  instruction: Instruction
}

/**
 * 警告事件（非致命错误）
 */
export interface WarningEvent {
  type: 'warning'
  text: string
}

/**
 * 错误事件（致命错误）
 */
export interface ErrorEvent {
  type: 'error'
  text: string
}

/**
 * 完成事件
 */
export interface DoneEvent {
  type: 'done'
  success?: boolean
  message?: string
}

/**
 * 流事件联合类型
 */
export type StreamEvent = ThinkingEvent | InstructionEvent | WarningEvent | ErrorEvent | DoneEvent

// ==================== 生成面板消息类型 ====================

/**
 * 生成面板消息类型
 */
export type GenerationMessageType = 'thinking' | 'action' | 'system' | 'user' | 'warning' | 'error'

/**
 * 生成面板消息
 */
export interface GenerationMessage {
  type: GenerationMessageType
  content: string
  timestamp: number
}
