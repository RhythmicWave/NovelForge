import request from './request'
import type { components } from '@renderer/types/generated'

export type Knowledge = components['schemas']['KnowledgeRead']
export type KnowledgeCreate = components['schemas']['KnowledgeCreate']
export type KnowledgeUpdate = components['schemas']['KnowledgeUpdate']

// 知识库 API（request 已解包 ApiResponse<T>，此处直接返回 T）
export async function listKnowledge(): Promise<Knowledge[]> {
  const resp = await request.get<Knowledge[]>('/knowledge')
  return resp
}

export async function createKnowledge(body: KnowledgeCreate): Promise<Knowledge> {
  const resp = await request.post<Knowledge>('/knowledge', body)
  return resp
}

export async function updateKnowledge(id: number, body: KnowledgeUpdate): Promise<Knowledge> {
  const resp = await request.put<Knowledge>(`/knowledge/${id}`, body)
  return resp
}

export async function deleteKnowledge(id: number): Promise<{ message: string }> {
  const resp = await request.delete<{ message?: string }>(`/knowledge/${id}`)
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

// --- 卡片类型 API ---
export type CardTypeRead = components['schemas']['CardTypeRead']
export type CardTypeCreate = components['schemas']['CardTypeCreate']
export type CardTypeUpdate = components['schemas']['CardTypeUpdate']
export async function listCardTypes(): Promise<CardTypeRead[]> { return await request.get<CardTypeRead[]>('/card-types') }
export async function createCardType(body: Partial<CardTypeCreate>): Promise<void> { await request.post('/card-types', body) }
export async function updateCardType(id: number, body: Partial<CardTypeUpdate>): Promise<void> { await request.put(`/card-types/${id}`, body) }
export async function deleteCardType(id: number): Promise<void> { await request.delete(`/card-types/${id}`) }

// --- 类型/卡片 Schema API ---
export async function getCardTypeSchema(id: number): Promise<any> { return await request.get(`/card-types/${id}/schema`) }
export async function updateCardTypeSchema(id: number, json_schema: any): Promise<any> { return await request.put(`/card-types/${id}/schema`, { json_schema }) }
export async function getCardSchema(id: number): Promise<any> { return await request.get(`/cards/${id}/schema`) }
export async function updateCardSchema(id: number, json_schema: any | null): Promise<any> { return await request.put(`/cards/${id}/schema`, { json_schema }) }
export async function applyCardSchemaToType(id: number): Promise<any> { return await request.post(`/cards/${id}/schema/apply-to-type`, {}) }

// --- 类型/卡片 AI 参数 API ---
export async function getCardTypeAIParams(id: number): Promise<any> { return await request.get(`/card-types/${id}/ai-params`) }
export async function updateCardTypeAIParams(id: number, ai_params: any | null): Promise<any> { return await request.put(`/card-types/${id}/ai-params`, { ai_params }) }
export async function getCardAIParams(id: number): Promise<any> { return await request.get(`/cards/${id}/ai-params`) }
export async function updateCardAIParams(id: number, ai_params: any | null): Promise<any> { return await request.put(`/cards/${id}/ai-params`, { ai_params }) }
export async function applyCardAIParamsToType(id: number): Promise<any> { return await request.post(`/cards/${id}/ai-params/apply-to-type`, {}) }

// --- 项目模板 API ---
export interface ProjectTemplateItem { id?: number; card_type_id: number; display_order: number; title_override?: string | null }
export interface ProjectTemplate { id: number; name: string; description?: string; built_in?: boolean; items: ProjectTemplateItem[] }
export interface ProjectTemplateCreate { name: string; description?: string; items: ProjectTemplateItem[] }
export interface ProjectTemplateUpdate { name?: string; description?: string; items?: ProjectTemplateItem[] }

export async function listProjectTemplates(): Promise<ProjectTemplate[]> {
  return await request.get<ProjectTemplate[]>('/project-templates')
}
export async function createProjectTemplate(body: ProjectTemplateCreate): Promise<ProjectTemplate> {
  return await request.post<ProjectTemplate>('/project-templates', body)
}
export async function updateProjectTemplate(id: number, body: ProjectTemplateUpdate): Promise<ProjectTemplate> {
  return await request.put<ProjectTemplate>(`/project-templates/${id}`, body)
}
export async function deleteProjectTemplate(id: number): Promise<{ message: string }> {
  const resp = await request.delete<{ message?: string }>(`/project-templates/${id}`)
  return { message: resp?.message || 'OK' } as any
}
