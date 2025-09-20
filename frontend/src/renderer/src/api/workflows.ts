import request from './request'

// 最小类型定义，避免过度耦合生成的类型
export interface WorkflowRead {
  id: number
  name: string
  description?: string | null
  version?: number
  dsl_version?: number
  is_built_in?: boolean
  is_active?: boolean
  definition_json?: any
  created_at?: string
  updated_at?: string
}

// 前端不再负责“预设/初始化创建”，仅保留读取/更新/删除与运行相关 API

export interface WorkflowUpdate {
  name?: string
  description?: string | null
  is_active?: boolean
  definition_json?: any
}

export interface WorkflowTriggerRead {
  id: number
  workflow_id: number
  trigger_on: string
  card_type_name?: string | null
  is_active: boolean
}

export interface WorkflowTriggerCreate {
  workflow_id: number
  trigger_on: string
  card_type_name?: string | null
  filter_json?: any
  is_active?: boolean
}

export interface WorkflowTriggerUpdate {
  trigger_on?: string
  card_type_name?: string | null
  filter_json?: any
  is_active?: boolean
}

export function listWorkflows(): Promise<WorkflowRead[]> {
  return request.get('/workflows', undefined, '/api', { showLoading: false })
}

export function getWorkflow(id: number): Promise<WorkflowRead> {
  return request.get(`/workflows/${id}`, undefined, '/api', { showLoading: false })
}

export function createWorkflow(payload: Partial<WorkflowRead> & { name: string; definition_json?: any }): Promise<WorkflowRead> {
  return request.post('/workflows', payload, '/api', { showLoading: false })
}

export function updateWorkflow(id: number, payload: WorkflowUpdate): Promise<WorkflowRead> {
  return request.put(`/workflows/${id}`, payload, '/api', { showLoading: false })
}

export function deleteWorkflow(id: number): Promise<void> {
  return request.delete(`/workflows/${id}`, undefined, '/api', { showLoading: false })
}

export function validateWorkflow(id: number): Promise<{ canonical_nodes: any[]; errors: string[] }> {
  return request.post(`/workflows/${id}/validate`, {}, '/api', { showLoading: false })
}

export function listWorkflowTriggers(): Promise<WorkflowTriggerRead[]> {
  return request.get('/workflow-triggers', undefined, '/api', { showLoading: false })
}

export function createWorkflowTrigger(payload: WorkflowTriggerCreate): Promise<WorkflowTriggerRead> {
  return request.post('/workflow-triggers', payload, '/api', { showLoading: false })
}

export function updateWorkflowTrigger(id: number, payload: WorkflowTriggerUpdate): Promise<WorkflowTriggerRead> {
  return request.put(`/workflow-triggers/${id}`, payload, '/api', { showLoading: false })
}

export function deleteWorkflowTrigger(id: number): Promise<void> {
  return request.delete(`/workflow-triggers/${id}`, undefined, '/api', { showLoading: false })
}


