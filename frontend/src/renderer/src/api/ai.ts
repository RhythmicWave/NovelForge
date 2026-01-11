import { aiHttpClient, API_BASE_URL } from './request'
import type { components } from '@renderer/types/generated'

export type GeneralAIRequest = components['schemas']['GeneralAIRequest']
export type ContinuationRequest = components['schemas']['ContinuationRequest']
export type ContinuationResponse = components['schemas']['ContinuationResponse']
export type AssistantChatRequest = components['schemas']['AssistantChatRequest']

// append_continuous_novel_directive（用于控制是否追加"连续小说正文"指令）
export type ContinuationRequestExtended = ContinuationRequest & { append_continuous_novel_directive?: boolean }

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

export function renderPromptWithKnowledge(name: string): Promise<{ text: string }> {
  return aiHttpClient.get<{ text: string }>(`/ai/prompts/render?name=${encodeURIComponent(name)}`)
}

export function assembleContext(body: AssembleContextRequest): Promise<AssembleContextResponse> {
  return aiHttpClient.post<AssembleContextResponse>('/context/assemble', body, '/api', { showLoading: false })
}

export function generateAIContent(
  params: GeneralAIRequest,
  options?: { signal?: AbortSignal }
): Promise<any> { // The response can be any of the Pydantic models
  return aiHttpClient.post<any>('/ai/generate', params, '/api', { showLoading: true, signal: options?.signal })
}

export function getAIConfigOptions(): Promise<AIConfigOptions> {
  return aiHttpClient.get<AIConfigOptions>('/ai/config-options')
}

export function generateContinuation(params: ContinuationRequestExtended): Promise<ContinuationResponse> {
  return aiHttpClient.post<ContinuationResponse>('/ai/generate/continuation', params, '/api', { showLoading: false })
}

function createStreamingRequest(
  endpoint: string,
  body: any,
  onData: (data: string) => void,
  onClose: () => void,
  onError?: (err: any) => void
) {
  const controller = new AbortController()
  const signal = controller.signal

  fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream'
    },
    body: JSON.stringify(body),
    signal
  }).then(async response => {
    if (!response.ok) {
      try {
        const ct = response.headers.get('content-type') || ''
        if (ct.includes('application/json')) {
          const data = await response.json()
          const msg = data?.message || data?.detail || `请求失败（${response.status}）`
          throw new Error(msg)
        } else {
          const text = await response.text()
          const msg = text || `请求失败（${response.status}）`
          throw new Error(msg)
        }
      } catch (e: any) {
        throw new Error(e?.message || `请求失败（${response.status}）`)
      }
    }
    if (!response.body) {
      throw new Error('Response body is null')
    }
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    function pump() {
      reader.read().then(({ done, value }) => {
        if (done) { onClose(); return }
        buffer += decoder.decode(value, { stream: true })
        const events = buffer.split('\n\n')
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
        if (err?.name === 'AbortError') { onClose(); return }
        onError?.(err)
      })
    }
    pump()
  }).catch(err => {
    if (err?.name === 'AbortError') { onClose(); return }
    onError?.(err)
  })

  return {
    cancel: () => { try { controller.abort() } catch {} }
  }
}

export function generateContinuationStreaming(
  params: ContinuationRequestExtended,
  onData: (data: string) => void,
  onClose: () => void,
  onError?: (err: any) => void
) {
  const endpoint = params.prompt_name === '灵感对话'
    ? `${API_BASE_URL}/ai/assistant/chat`
    : `${API_BASE_URL}/ai/generate/continuation`
  return createStreamingRequest(endpoint, params, onData, onClose, onError)
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

/**
 * 灵感助手专用流式对话
 */
export function generateAssistantChatStreaming(
  params: AssistantChatRequest,
  onData: (data: string) => void,
  onClose: () => void,
  onError?: (err: any) => void
) {
  return createStreamingRequest(`${API_BASE_URL}/ai/assistant/chat`, params, onData, onClose, onError)
}