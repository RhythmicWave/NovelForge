/**
 * 工作流进度管理 Composable
 * 
 * 统一管理工作流执行进度，供执行界面和状态栏共用
 * 注意：SSE 连接管理已移到 WorkflowStatusStore 中，确保切换界面时连接不断
 */

import { useWorkflowStore } from '@/stores/useWorkflowStore'
import type { WorkflowStreamCallbacks } from '@/api/workflows'

export function useWorkflowProgress() {
  const workflowStore = useWorkflowStore()

  /**
   * 启动工作流执行（全局 SSE 连接管理）
   */
  async function startWorkflow(
    workflowId: number,
    workflowName: string,
    callbacks: WorkflowStreamCallbacks,
    resume: boolean = false,
    runId?: number
  ) {
    return await workflowStore.startWorkflowExecution(
      workflowId,
      workflowName,
      callbacks,
      resume,
      runId
    )
  }

  /**
   * 暂停工作流执行
   */
  function pauseWorkflow(runId: number) {
    workflowStore.pauseWorkflowExecution(runId)
  }

  /**
   * 获取 SSE 连接
   */
  function getConnection(runId: number) {
    return workflowStore.getSSEConnection(runId)
  }

  return {
    startWorkflow,
    pauseWorkflow,
    getConnection
  }
}
