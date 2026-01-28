import request from './request'
import type { components } from '@renderer/types/generated'

export type ProjectRead = components['schemas']['ProjectRead']
export type ProjectCreate = components['schemas']['ProjectCreate']
export type ProjectUpdate = components['schemas']['ProjectUpdate']

export const getFreeProject = async (): Promise<ProjectRead> => {
  try {
    return await request.get('/projects/free')
  } catch (err) {
    // 兼容后端未更新路由顺序导致 /free 命中 /{project_id} 的情况：回退到列表查找
    const list = await request.get<ProjectRead[]>('/projects')
    const found = (list || []).find(p => (p.name || '') === '__free__')
    if (!found) throw err
    return found
  }
}

export const getProjects = (): Promise<ProjectRead[]> => {
  return request.get('/projects')
}

export const createProject = (data: ProjectCreate): Promise<ProjectRead> => {
  return request.post('/projects/', data)
}

export const updateProject = (id: number, data: ProjectUpdate): Promise<void> => {
  return request.put(`/projects/${id}`, data)
}

export const deleteProject = (id: number): Promise<void> => {
  return request.delete(`/projects/${id}`)
} 