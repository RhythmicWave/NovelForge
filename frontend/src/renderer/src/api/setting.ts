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
