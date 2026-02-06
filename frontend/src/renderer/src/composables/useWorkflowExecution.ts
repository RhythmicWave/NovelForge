/**
 * 工作流执行状态机
 * 
 * 管理工作流执行的状态转换，防止非法操作
 */

import { reactive, readonly, computed } from 'vue'

export enum WorkflowState {
  IDLE = 'idle',           // 空闲状态
  RUNNING = 'running',     // 运行中
  PAUSED = 'paused',       // 已暂停
  COMPLETED = 'completed', // 已完成
  FAILED = 'failed'        // 失败
}

export interface WorkflowExecution {
  state: WorkflowState
  runId: number | null
  workflowId: number | null
  error: string | null
}

/**
 * 工作流执行状态机
 */
export function useWorkflowExecution() {
  // 内部状态
  const execution = reactive<WorkflowExecution>({
    state: WorkflowState.IDLE,
    runId: null,
    workflowId: null,
    error: null
  })

  // 状态转换规则
  const validTransitions: Record<WorkflowState, WorkflowState[]> = {
    [WorkflowState.IDLE]: [WorkflowState.RUNNING],
    [WorkflowState.RUNNING]: [WorkflowState.PAUSED, WorkflowState.COMPLETED, WorkflowState.FAILED],
    [WorkflowState.PAUSED]: [WorkflowState.RUNNING, WorkflowState.FAILED],
    [WorkflowState.COMPLETED]: [WorkflowState.IDLE, WorkflowState.RUNNING],  // 允许从完成状态直接开始新执行
    [WorkflowState.FAILED]: [WorkflowState.IDLE, WorkflowState.RUNNING]      // 允许从失败状态直接开始新执行
  }

  // 计算属性
  const isRunning = computed(() => execution.state === WorkflowState.RUNNING)
  const isPaused = computed(() => execution.state === WorkflowState.PAUSED)
  const isIdle = computed(() => execution.state === WorkflowState.IDLE)
  const isCompleted = computed(() => execution.state === WorkflowState.COMPLETED)
  const isFailed = computed(() => execution.state === WorkflowState.FAILED)
  const canPause = computed(() => execution.state === WorkflowState.RUNNING)
  const canResume = computed(() => execution.state === WorkflowState.PAUSED)
  const canStart = computed(() => 
    execution.state === WorkflowState.IDLE || 
    execution.state === WorkflowState.COMPLETED || 
    execution.state === WorkflowState.FAILED
  )

  /**
   * 状态转换
   * @param newState 新状态
   * @throws Error 如果状态转换非法
   */
  function transitionTo(newState: WorkflowState) {
    const currentState = execution.state
    const allowedStates = validTransitions[currentState]

    if (!allowedStates.includes(newState)) {
      throw new Error(
        `非法状态转换: ${currentState} -> ${newState}. ` +
        `允许的转换: ${allowedStates.join(', ')}`
      )
    }

    console.log(`[WorkflowExecution] 状态转换: ${currentState} -> ${newState}`)
    execution.state = newState
  }

  /**
   * 开始执行
   * @param workflowId 工作流ID
   * @param runId 运行ID
   */
  function start(workflowId: number, runId: number) {
    // 如果当前是完成或失败状态，先重置再开始（自动清空之前的结果）
    if (execution.state === WorkflowState.COMPLETED || execution.state === WorkflowState.FAILED) {
      console.log(`[WorkflowExecution] 从 ${execution.state} 状态重新开始，自动清空结果`)
    }
    
    transitionTo(WorkflowState.RUNNING)
    execution.workflowId = workflowId
    execution.runId = runId
    execution.error = null
  }

  /**
   * 更新运行ID（不改变状态）
   * @param runId 新的运行ID
   */
  function updateRunId(runId: number) {
    console.log(`[WorkflowExecution] 更新 runId: ${execution.runId} -> ${runId}`)
    execution.runId = runId
  }

  /**
   * 暂停执行
   */
  function pause() {
    transitionTo(WorkflowState.PAUSED)
  }

  /**
   * 恢复执行
   */
  function resume() {
    transitionTo(WorkflowState.RUNNING)
  }

  /**
   * 完成执行
   */
  function complete() {
    transitionTo(WorkflowState.COMPLETED)
  }

  /**
   * 执行失败
   * @param error 错误信息
   */
  function fail(error: string) {
    transitionTo(WorkflowState.FAILED)
    execution.error = error
  }

  /**
   * 重置状态
   */
  function reset() {
    transitionTo(WorkflowState.IDLE)
    execution.runId = null
    execution.workflowId = null
    execution.error = null
  }

  return {
    // 只读状态
    execution: readonly(execution),
    
    // 计算属性
    isRunning,
    isPaused,
    isIdle,
    isCompleted,
    isFailed,
    canPause,
    canResume,
    canStart,
    
    // 状态转换方法
    start,
    updateRunId,
    pause,
    resume,
    complete,
    fail,
    reset
  }
}
