import request from './request'
import type { components } from '@renderer/types/generated'

export type Knowledge = components['schemas']['KnowledgeRead']
export type KnowledgeCreate = components['schemas']['KnowledgeCreate']
export type KnowledgeUpdate = components['schemas']['KnowledgeUpdate']

// 知识库 API（返回已解包的数据）
export async function listKnowledge(): Promise<Knowledge[]> {
  const resp = await request.get<components['schemas']['ApiResponse_List_KnowledgeRead__']>('/knowledge')
  return (resp?.data || []) as Knowledge[]
}

export async function createKnowledge(body: KnowledgeCreate): Promise<Knowledge> {
  const resp = await request.post<components['schemas']['ApiResponse_KnowledgeRead_']>('/knowledge', body)
  return (resp?.data as Knowledge)
}

export async function updateKnowledge(id: number, body: KnowledgeUpdate): Promise<Knowledge> {
  const resp = await request.put<components['schemas']['ApiResponse_KnowledgeRead_']>(`/knowledge/${id}`, body)
  return (resp?.data as Knowledge)
}

export async function deleteKnowledge(id: number): Promise<{ message: string }> {
  const resp = await request.delete<components['schemas']['ApiResponse']>(`/knowledge/${id}`)
  return { message: resp?.message || 'OK' } as any
}

// --- LLM 配置 API ---
export type LLMConfigRead = components['schemas']['LLMConfigRead']
export type LLMConfigCreate = components['schemas']['LLMConfigCreate']
export type LLMConfigUpdate = components['schemas']['LLMConfigUpdate']

export async function listLLMConfigs(): Promise<LLMConfigRead[]> {
  return await request.get<LLMConfigRead[]>('/llm-configs/')
}
export async function createLLMConfig(body: LLMConfigCreate): Promise<void> {
  await request.post('/llm-configs/', body)
}
export async function updateLLMConfig(id: number, body: LLMConfigUpdate): Promise<void> {
  await request.put(`/llm-configs/${id}`, body)
}
export async function deleteLLMConfig(id: number): Promise<void> {
  await request.delete(`/llm-configs/${id}`)
}

// --- 提示词 API ---
export interface Prompt { id: number; name: string; description: string; template: string; built_in?: boolean }
export async function listPrompts(): Promise<Prompt[]> { return await request.get<Prompt[]>('/prompts') }
export async function createPrompt(body: Partial<Prompt>): Promise<void> { await request.post('/prompts', body) }
export async function updatePrompt(id: number, body: Partial<Prompt>): Promise<void> { await request.put(`/prompts/${id}`, body) }
export async function deletePrompt(id: number): Promise<void> { await request.delete(`/prompts/${id}`) }

// --- 输出模型 API ---
export interface OutputModel { id?: number; name: string; description?: string | null; json_schema?: any; built_in?: boolean; version?: number }
export async function listOutputModels(): Promise<OutputModel[]> { return await request.get<OutputModel[]>('/output-models/') }
export async function createOutputModel(body: OutputModel): Promise<void> { await request.post('/output-models', body) }
export async function updateOutputModel(id: number, body: OutputModel): Promise<void> { await request.put(`/output-models/${id}`, body) }
export async function deleteOutputModel(id: number): Promise<void> { await request.delete(`/output-models/${id}`) }

// --- 卡片类型 API ---
export type CardTypeRead = components['schemas']['CardTypeRead']
export type CardTypeCreate = components['schemas']['CardTypeCreate']
export type CardTypeUpdate = components['schemas']['CardTypeUpdate']
export async function listCardTypes(): Promise<CardTypeRead[]> { return await request.get<CardTypeRead[]>('/card-types') }
export async function createCardType(body: Partial<CardTypeCreate>): Promise<void> { await request.post('/card-types', body) }
export async function updateCardType(id: number, body: Partial<CardTypeUpdate>): Promise<void> { await request.put(`/card-types/${id}`, body) }
export async function deleteCardType(id: number): Promise<void> { await request.delete(`/card-types/${id}`) }
