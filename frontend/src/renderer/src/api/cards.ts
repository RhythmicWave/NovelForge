import request from './request'
import type { components } from '@renderer/types/generated'
import type { AxiosResponse } from 'axios'

// --- Type Aliases for easier use ---
export type CardTypeRead = components['schemas']['CardTypeRead']
export type CardTypeCreate = components['schemas']['CardTypeCreate']
export type CardTypeUpdate = components['schemas']['CardTypeUpdate']
export type CardRead = components['schemas']['CardRead']
export type CardCreate = Omit<components['schemas']['CardCreate'], 'content'> & { content?: any | null }
export type CardUpdate = components['schemas']['CardUpdate']

// --- CardType API ---
export const getCardTypes = (): Promise<CardTypeRead[]> => request.get('/card-types')
export const createCardType = (data: CardTypeCreate): Promise<CardTypeRead> => request.post('/card-types', data)
export const updateCardType = (id: number, data: CardTypeUpdate): Promise<CardTypeRead> => request.put(`/card-types/${id}`, data)
export const deleteCardType = (id: number): Promise<void> => request.delete(`/card-types/${id}`)

// --- Card API ---
export const getCardsForProject = (projectId: number): Promise<CardRead[]> => request.get(`/projects/${projectId}/cards`)
export const createCard = (projectId: number, data: CardCreate): Promise<CardRead> => request.post(`/projects/${projectId}/cards`, data)
export const updateCard = (id: number, data: CardUpdate): Promise<CardRead> => request.put(`/cards/${id}`, data)
// 原始响应：用于读取 X-Workflows-Started
export const updateCardRaw = (id: number, data: CardUpdate): Promise<AxiosResponse<CardRead>> => (request as any).request({ method: 'PUT', url: `/api/cards/${id}`, data, rawResponse: true })

// 批量更新卡片排序
export interface CardOrderItem {
  card_id: number
  display_order: number
  parent_id?: number | null
}
export interface CardBatchReorderRequest {
  updates: CardOrderItem[]
}
export interface CardBatchReorderResponse {
  success: boolean
  updated_count: number
  message: string
}
export const batchReorderCards = (data: CardBatchReorderRequest): Promise<CardBatchReorderResponse> => 
  request.post('/cards/batch-reorder', data)

export const deleteCard = (id: number): Promise<void> => request.delete(`/cards/${id}`)
export const copyCard = (id: number, params: { target_project_id: number; parent_id?: number | null }): Promise<CardRead> => request.post(`/cards/${id}/copy`, params)
export const moveCard = (id: number, params: { target_project_id: number; parent_id?: number | null }): Promise<CardRead> => request.post(`/cards/${id}/move`, params)

// --- AI Content Models API ---
export const getContentModels = (): Promise<string[]> => request.get('/ai/content-models')

// --- Card AI Params API ---
export const getCardAIParams = (cardId: number): Promise<{ ai_params: any; effective_params: any; follow_type: boolean }> => request.get(`/cards/${cardId}/ai-params`) 