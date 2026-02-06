import request, { API_BASE_URL } from './request'
import type { components } from '@/types/generated'

// ============================================================
// 类型定义 - 全部使用自动生成的类型
// ============================================================
// 所有类型都从 OpenAPI schema 自动生成
// 后端修改后运行 `npm run gen:types` 即可同步
// ============================================================

export type WorkflowRead = components['schemas']['WorkflowRead']
export type WorkflowUpdate = components['schemas']['WorkflowUpdate']
export type WorkflowRunRead = components['schemas']['WorkflowRunRead']
export type NodeExecutionStatus = components['schemas']['NodeExecutionStatus']

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

export function deleteRun(runId: number): Promise<{ ok: boolean; message: string }> {
  return request.delete(`/workflows/runs/${runId}`, undefined, '/api')
}

export interface ValidationError {
  line: number
  variable: string
  error_type: string
  message: string
  suggestion?: string
}

export interface ValidationResult {
  is_valid: boolean
  errors: ValidationError[]
  warnings: ValidationError[]
}

export function validateWorkflow(id: number): Promise<ValidationResult> {
  return request.post(`/workflows/${id}/validate`, {}, '/api', { showLoading: false })
}


export interface WorkflowNodePort {
  name: string
  type: string
  description: string
  required?: boolean
}

export interface WorkflowNodeType {
  type: string
  category: string
  label: string
  description: string
  inputs: WorkflowNodePort[]
  outputs: WorkflowNodePort[]
  config_schema: any
}

export function getNodeTypes(): Promise<{ node_types: WorkflowNodeType[] }> {
  return request.get('/nodes/types', undefined, '/api', { showLoading: false })
}



// ============================================================
// API 函数
// ============================================================

// 获取运行详情
export function getRun(runId: number): Promise<WorkflowRunRead> {
  return request.get(`/workflows/runs/${runId}`, undefined, '/api', { showLoading: false })
}

// 获取所有运行记录
export function listAllRuns(params?: { limit?: number; offset?: number; status?: string }): Promise<WorkflowRunRead[]> {
  return request.get('/runs', params, '/api', { showLoading: false })
}

// 取消运行
export function cancelRun(runId: number): Promise<{ ok: boolean; message?: string }> {
  return request.post(`/workflows/runs/${runId}/cancel`, {}, '/api')
}

// ============================================================
// 代码式工作流 API
// ============================================================

export interface WorkflowStatement {
  variable: string
  code: string
}

export interface ProgressEvent {
  type: 'progress'
  statement: WorkflowStatement
  percent: number
  message: string
  stage?: string
}

export interface CompleteEvent {
  type: 'complete'
  statement: WorkflowStatement
  result: any
}

export interface ErrorEvent {
  type: 'error'
  statement: WorkflowStatement
  error: string
}

export interface StartEvent {
  type: 'start'
  statement: WorkflowStatement
}

export type WorkflowStreamEvent = StartEvent | ProgressEvent | CompleteEvent | ErrorEvent

export interface WorkflowStreamCallbacks {
  onRunStarted?: (runId: number) => void
  onStart?: (event: StartEvent) => void
  onProgress?: (event: ProgressEvent) => void
  onComplete?: (event: CompleteEvent) => void
  onError?: (event: ErrorEvent) => void
  onEnd?: () => void
}

/**
 * 执行代码式工作流（流式SSE推送）
 * 
 * @param workflowId 工作流ID
 * @param callbacks 事件回调
 * @param resume 是否恢复执行（默认 false）
 * @param runId 恢复执行时的 run ID（resume=true 时必须提供）
 * @returns 包含 runId 和 EventSource 的对象
 */
export async function runCodeWorkflowStream(
  workflowId: number,
  callbacks: WorkflowStreamCallbacks,
  resume: boolean = false,
  runId?: number
): Promise<{ runId: { value: number }; eventSource: EventSource }> {
  console.log('[API] 开始执行工作流:', workflowId, 'resume:', resume, 'runId:', runId)
  
  // 构建 URL
  let url = `${API_BASE_URL}/workflows/${workflowId}/execute-stream`
  if (resume && runId) {
    url += `?resume=true&run_id=${runId}`
  }
  
  console.log('[API] 连接 SSE:', url)

  // EventSource 不支持 AbortController，直接使用 close() 方法中断
  const eventSource = new EventSource(url)
  // 使用对象包装 runId，使其可以被外部引用更新
  const runIdRef = { value: runId || 0 }

  eventSource.onopen = () => {
    console.log('[API] SSE 连接成功')
  }

  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      console.log('[API] 收到消息:', data)
      
      // 处理不同类型的事件
      switch (data.type) {
        case 'run_started':
          // 保存 run_id
          runIdRef.value = data.run_id
          console.log('[API] 运行已启动, run_id:', runIdRef.value)
          // 调用回调
          callbacks.onRunStarted?.(runIdRef.value)
          break
          
        case 'start':
          callbacks.onStart?.(data as StartEvent)
          break
          
        case 'progress':
          callbacks.onProgress?.(data as ProgressEvent)
          break
          
        case 'complete':
          callbacks.onComplete?.(data as CompleteEvent)
          break
          
        case 'error':
          callbacks.onError?.(data as ErrorEvent)
          break
          
        case 'paused':
          console.log('[API] 工作流已暂停')
          callbacks.onEnd?.()
          eventSource.close()
          break
          
        case 'end':
          callbacks.onEnd?.()
          eventSource.close()
          break
          
        default:
          console.warn('[API] 未知事件类型:', data.type)
      }
    } catch (error) {
      console.error('[API] 解析消息失败:', error)
    }
  }

  eventSource.onerror = (error) => {
    console.error('[API] SSE 错误:', error)
    
    // 检查 readyState 判断是否是正常关闭
    if (eventSource.readyState === EventSource.CLOSED) {
      console.log('[API] SSE 连接已关闭（可能是暂停或完成）')
      // 不调用 onError，避免误报错误
      return
    }
    
    // 立即关闭连接，防止自动重连
    eventSource.close()
    
    callbacks.onError?.({
      type: 'error',
      statement: { variable: 'unknown', code: 'unknown' },
      error: 'SSE connection error'
    })
    callbacks.onEnd?.()
  }

  return { runId: runIdRef, eventSource }
}

/**
 * 解析工作流代码（验证语法）
 * @param code 工作流代码
 * @returns 解析结果
 */
export async function parseWorkflowCode(code: string): Promise<{
  success: boolean
  statements?: WorkflowStatement[]
  errors?: string[]
}> {
  return request.post('/workflows/parse', { code }, '/api', { showLoading: false })
}

/**
 * 保存代码式工作流
 * @param name 工作流名称
 * @param code 工作流代码
 * @returns 保存的工作流
 */
export async function saveCodeWorkflow(name: string, code: string): Promise<WorkflowRead> {
  return request.post('/workflows/code', { name, code }, '/api')
}

/**
 * 获取代码式工作流
 * @param id 工作流 ID
 * @returns 工作流代码
 */
export async function getCodeWorkflow(id: number): Promise<{ id: number; name: string; code: string }> {
  return request.get(`/workflows/${id}/code`, undefined, '/api', { showLoading: false })
}

// 获取项目创建模板列表
export interface ProjectTemplate {
  workflow_id: number
  workflow_name: string
  template: string | null
  description?: string
}

export function getProjectTemplates(): Promise<{ templates: ProjectTemplate[] }> {
  return request.get('/workflows/project-templates', undefined, '/api', { showLoading: false })
}
