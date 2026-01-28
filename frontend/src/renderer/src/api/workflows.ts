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
export type RunRequest = components['schemas']['RunRequest']
export type NodeExecutionStatus = components['schemas']['NodeExecutionStatus']
export type RunStatus = components['schemas']['RunStatus']

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

// 启动工作流运行
export async function runWorkflow(workflowId: number, payload: RunRequest = {}): Promise<WorkflowRunRead> {
  console.log('[API] runWorkflow 调用, workflowId:', workflowId, 'payload:', payload)
  const result = await request.post<WorkflowRunRead>(`/workflows/${workflowId}/run`, payload, '/api')
  console.log('[API] runWorkflow 返回:', result)
  return result
}

// 获取运行状态
export function getRunStatus(runId: number): Promise<RunStatus> {
  return request.get(`/workflows/runs/${runId}/status`, undefined, '/api', { showLoading: false })
}

// 获取运行详情
export function getRun(runId: number): Promise<WorkflowRunRead> {
  return request.get(`/workflows/runs/${runId}`, undefined, '/api', { showLoading: false })
}

// 取消运行
export function cancelRun(runId: number): Promise<{ ok: boolean; message?: string }> {
  return request.post(`/workflows/runs/${runId}/cancel`, {}, '/api')
}

/**
 * 连接工作流运行事件流（SSE）
 * @param runId 运行 ID
 * @param onMessage 消息回调
 * @param onError 错误回调
 * @param onOpen 连接成功回调
 * @returns EventSource 实例，用于关闭连接
 */
export function connectRunEvents(
  runId: number,
  onMessage: (data: any) => void,
  onError?: (error: Event) => void,
  onOpen?: () => void
): EventSource {
  const url = `${API_BASE_URL}/workflows/runs/${runId}/events`
  console.log('[API] 连接 SSE 事件流:', url)

  const eventSource = new EventSource(url)

  eventSource.onopen = () => {
    console.log('[API] SSE 连接成功')
    onOpen?.()
  }

  eventSource.onmessage = (event) => {
    console.log('[API] SSE 收到消息')
    try {
      const status = JSON.parse(event.data)

      // 检查错误
      if (status.error) {
        console.error('[API] SSE 错误:', status.error)
        return
      }

      // 直接传递状态对象
      onMessage(status)
    } catch (e) {
      console.error('[API] SSE 解析消息失败:', e)
    }
  }

  eventSource.onerror = (error) => {
    console.error('[API] SSE 连接错误:', error)
    onError?.(error)
  }

  return eventSource
}
