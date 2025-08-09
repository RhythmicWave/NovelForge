import request from './request'
import type { components } from '@renderer/types/generated'

// --- Type Aliases for easier use ---
export type CardTypeRead = components['schemas']['CardTypeRead']
export type CardTypeCreate = components['schemas']['CardTypeCreate']
export type CardTypeUpdate = components['schemas']['CardTypeUpdate']
export type CardRead = components['schemas']['CardRead']
export type CardCreate = Omit<components['schemas']['CardCreate'], 'content'> & { content?: any | null }
export type CardUpdate = components['schemas']['CardUpdate']


// --- CardType API ---

export const getCardTypes = (): Promise<CardTypeRead[]> => {
  return request.get('/card-types')
}

export const createCardType = (data: CardTypeCreate): Promise<CardTypeRead> => {
  return request.post('/card-types', data)
}

export const updateCardType = (id: number, data: CardTypeUpdate): Promise<CardTypeRead> => {
  return request.put(`/card-types/${id}`, data)
}

export const deleteCardType = (id: number): Promise<void> => {
  return request.delete(`/card-types/${id}`)
}


// --- Card API ---

export const getCardsForProject = (projectId: number): Promise<CardRead[]> => {
  return request.get(`/projects/${projectId}/cards`)
}

export const createCard = (projectId: number, data: CardCreate): Promise<CardRead> => {
  return request.post(`/projects/${projectId}/cards`, data)
}

export const updateCard = (id: number, data: CardUpdate): Promise<CardRead> => {
  return request.put(`/cards/${id}`, data)
}

export const deleteCard = (id: number): Promise<void> => {
  return request.delete(`/cards/${id}`)
}

// --- AI Content Models API ---

export const getContentModels = (): Promise<string[]> => {
  return request.get('/ai/content-models')
} 