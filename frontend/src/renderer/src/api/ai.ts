import { aiHttpClient } from './request'
import type { components } from '@renderer/types/generated'

export type GeneralAIRequest = components['schemas']['GeneralAIRequest']
export type ContinuationRequest = components['schemas']['ContinuationRequest']
export type ContinuationResponse = components['schemas']['ContinuationResponse']

// Manually define AIConfigOptions if it's not in generated types
export interface AIConfigOptions {
  llm_configs: Array<{ id: number; display_name: string }>
  prompts: Array<{ id: number; name: string; description: string | null; built_in?: boolean }>
  available_tasks?: string[]
  response_models: string[]
}

// 使用后端生成的类型
export type AssembleContextRequest = components['schemas']['AssembleContextRequest']
export type AssembleContextResponse = components['schemas']['AssembleContextResponse']


export function assembleContext(body: AssembleContextRequest): Promise<AssembleContextResponse> {
  return aiHttpClient.post<AssembleContextResponse>('/context/assemble', body, '/api', { showLoading: false })
}

export function generateAIContent(
  params: GeneralAIRequest
): Promise<any> { // The response can be any of the Pydantic models
  return aiHttpClient.post<any>('/ai/generate', params)
}

export function getAIConfigOptions(): Promise<AIConfigOptions> {
  return aiHttpClient.get<AIConfigOptions>('/ai/config-options')
}

export function generateContinuation(params: ContinuationRequest): Promise<ContinuationResponse> {
  return aiHttpClient.post<ContinuationResponse>('/ai/generate/continuation', params, '/api', { showLoading: false })
}

export function generateContinuationStreaming(
    params: ContinuationRequest, 
    onData: (data: string) => void, 
    onClose: () => void,
    onError?: (err: any) => void
) {
  const API_BASE_URL = 'http://127.0.0.1:8000/api'
  const controller = new AbortController()
  const signal = controller.signal
  fetch(`${API_BASE_URL}/ai/generate/continuation`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream'
    },
    body: JSON.stringify(params),
    signal,
  }).then(response => {
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    if (!response.body) {
        throw new Error('Response body is null');
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = ''
    function pump() {
      reader.read().then(({ done, value }) => {
        if (done) { onClose(); return }
        buffer += decoder.decode(value, { stream: true })
        // 按行解析标准 SSE：可能出现 data: 多行，空行表示一次事件结束
        const events = buffer.split('\n\n')
        // 保留最后一个不完整事件在 buffer
        buffer = events.pop() || ''
        for (const evt of events) {
          const lines = evt.split('\n').map(l => l.trim())
          const dataLines = lines.filter(l => l.startsWith('data: ')).map(l => l.substring(6))
          if (!dataLines.length) continue
          try {
            const payload = JSON.parse(dataLines.join(''))
            if (typeof payload.content === 'string' && payload.content.length) onData(payload.content)
          } catch {}
        }
        pump()
      }).catch(err => { 
        // fetch 中断时，reader.read 会抛异常；此时视为正常关闭
        if ((err as any)?.name === 'AbortError') { onClose(); return }
        if (onError) onError(err) 
      })
    }
    pump();
  }).catch(err => {
    if (onError) onError(err);
  });
  return {
    cancel: () => { try { controller.abort() } catch {} }
  }
}

// 伏笔建议（占位）
export interface ForeshadowResponse { goals: string[]; items: string[]; persons: string[] }
export function foreshadowSuggest(text: string): Promise<ForeshadowResponse> {
  return aiHttpClient.post<ForeshadowResponse>('/foreshadow/suggest', { text })
}

// 伏笔登记 CRUD
export interface ForeshadowItem {
  id: number
  project_id: number
  chapter_id?: number | null
  title: string
  type: 'goal' | 'item' | 'person' | 'other'
  note?: string | null
  status: 'open' | 'resolved'
  created_at: string
  resolved_at?: string | null
}
export interface ForeshadowListResponse { items: ForeshadowItem[] }
export function listForeshadow(projectId: number, status?: 'open' | 'resolved'): Promise<ForeshadowListResponse> {
  const qs = new URLSearchParams({ project_id: String(projectId), ...(status ? { status } : {}) })
  return aiHttpClient.get<ForeshadowListResponse>(`/foreshadow/list?${qs.toString()}`)
}
export function registerForeshadow(projectId: number, items: Array<{ title: string; type?: 'goal' | 'item' | 'person' | 'other'; note?: string; chapter_id?: number }>): Promise<ForeshadowListResponse> {
  return aiHttpClient.post<ForeshadowListResponse>('/foreshadow/register', { project_id: projectId, items })
}
export function resolveForeshadow(projectId: number, itemId: number): Promise<ForeshadowItem> {
  return aiHttpClient.post<ForeshadowItem>(`/foreshadow/resolve/${itemId}`, { project_id: projectId })
}
export function deleteForeshadow(projectId: number, itemId: number): Promise<{ success: boolean }> {
  return aiHttpClient.post<{ success: boolean }>(`/foreshadow/delete/${itemId}`, { project_id: projectId })
} 

 