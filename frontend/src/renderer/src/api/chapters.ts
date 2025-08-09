import request from './request'
import type { components } from '../types/generated'

type Chapter = components['schemas']['ChapterRead']
type ChapterCreate = components['schemas']['ChapterCreate']
type ChapterUpdate = components['schemas']['ChapterUpdate']

export const chapterApi = {
  getForVolume: (volumeId: number): Promise<Chapter[]> => {
    return request.get(`/chapters/by_volume/${volumeId}`)
  },
  
  create: (data: ChapterCreate): Promise<Chapter> => {
    // The 'content' field in ChapterCreate is optional, so we provide a default empty object if not present.
    const payload: ChapterCreate = {
      title: data.title,
      volume_id: data.volume_id,
      content: data.content || { type: 'doc', content: [{ type: 'paragraph' }] }
    };
    return request.post('/chapters/', payload)
  },

  update: (chapterId: number, data: ChapterUpdate): Promise<Chapter> => {
    return request.put(`/chapters/${chapterId}`, data)
  },
  
  delete: (chapterId: number): Promise<void> => {
    return request.delete(`/chapters/${chapterId}`)
  }
} 