/**
 * 指令流生成 API
 * 
 * 封装了与后端指令流生成端点的通信
 */

import type {
  InstructionGenerateRequest,
  StreamEvent,
  Instruction
} from '@renderer/types/instruction'

/**
 * 生成参数
 */
export interface GenerateParams extends InstructionGenerateRequest {
  // 继承所有请求参数
}

/**
 * 事件回调函数类型
 */
export interface GenerateCallbacks {
  onThinking?: (text: string) => void
  onInstruction?: (instruction: Instruction) => void
  onWarning?: (text: string) => void
  onError?: (text: string) => void
  onDone?: (success: boolean, message?: string) => void
}

/**
 * 使用指令流生成
 * 
 * @param params 生成参数
 * @param callbacks 事件回调
 * @param signal 中断信号（可选）
 */
export async function generateWithInstructionStream(
  params: GenerateParams,
  callbacks: GenerateCallbacks,
  signal?: AbortSignal
): Promise<void> {
  const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'
  const url = `${API_BASE}/api/ai/generate/stream`

  try {
    // 发送 POST 请求
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(params),
      signal
    })

    if (!response.ok) {
      const errorText = await response.text()
      throw new Error(`HTTP ${response.status}: ${errorText}`)
    }

    if (!response.body) {
      throw new Error('响应体为空')
    }

    // 读取 SSE 流
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()

      if (done) {
        break
      }

      // 解码数据块
      buffer += decoder.decode(value, { stream: true })

      // 按行分割
      const lines = buffer.split('\n')
      buffer = lines.pop() || '' // 保留不完整的行

      for (const line of lines) {
        if (!line.trim()) {
          continue
        }

        // 解析 SSE 格式
        const event = parseSSELine(line)
        if (event) {
          handleEvent(event, callbacks)
        }
      }
    }

    // 处理剩余的缓冲区
    if (buffer.trim()) {
      const event = parseSSELine(buffer)
      if (event) {
        handleEvent(event, callbacks)
      }
    }
  } catch (error: any) {
    if (error.name === 'AbortError') {
      console.log('生成已中断')
      return
    }

    console.error('生成失败:', error)
    callbacks.onError?.(error.message || '生成失败')
  }
}

/**
 * 解析 SSE 行
 * @param line SSE 格式的行
 * @returns 解析后的事件对象
 */
function parseSSELine(line: string): { event: string; data: any } | null {
  // SSE 格式：event: xxx\ndata: {...}
  // 或者简化格式：data: {...}

  let eventType = 'message'
  let dataStr = ''

  const lines = line.split('\n')
  for (const l of lines) {
    if (l.startsWith('event:')) {
      eventType = l.slice(6).trim()
    } else if (l.startsWith('data:')) {
      dataStr = l.slice(5).trim()
    }
  }

  if (!dataStr) {
    return null
  }

  try {
    const data = JSON.parse(dataStr)
    return { event: eventType, data }
  } catch (e) {
    console.warn('解析 SSE 数据失败:', dataStr)
    return null
  }
}

/**
 * 处理事件
 * @param event 事件对象
 * @param callbacks 回调函数
 */
function handleEvent(event: { event: string; data: any }, callbacks: GenerateCallbacks): void {
  const { data } = event
  const type = data.type || event.event

  switch (type) {
    case 'thinking':
      callbacks.onThinking?.(data.text)
      break

    case 'instruction':
      callbacks.onInstruction?.(data.instruction)
      break

    case 'warning':
      callbacks.onWarning?.(data.text)
      break

    case 'error':
      callbacks.onError?.(data.text)
      break

    case 'done':
      callbacks.onDone?.(data.success !== false, data.message)
      break

    default:
      console.warn('未知的事件类型:', type, data)
  }
}
