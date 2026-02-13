import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { 
    getRun, 
    runCodeWorkflowStream, 
    getNodeTypes,
    type WorkflowStreamCallbacks,
    type WorkflowNodeType 
} from '@/api/workflows'

// 简单的运行信息接口，用于状态栏显示
export interface RunInfo {
    id: number
    workflow_id: number
    workflow_name?: string
    status: string
    created_at?: string
    error?: string // 从 error_json 提取的错误信息
    current_node?: string // 当前执行的节点
    progress?: number // 执行进度（0-100）
}

// SSE 连接管理
interface SSEConnection {
    runId: number
    workflowId: number
    workflowName: string
    eventSource: EventSource
    callbacks: WorkflowStreamCallbacks
}

/**
 * 统一的工作流 Store
 * 管理：
 * 1. 节点类型、卡片类型等元数据
 * 2. 工作流运行状态和 SSE 连接
 */
export const useWorkflowStore = defineStore('workflow', () => {
    // ==================== 元数据管理 ====================
    const nodeTypes = ref<WorkflowNodeType[]>([])
    const cardTypes = ref<any[]>([])
    const isLoadingNodeTypes = ref(false)

    // Getters
    const categories = computed(() => {
        const cats = new Set(nodeTypes.value.map(n => n.category))
        return Array.from(cats)
    })

    const getNodesByCategory = (category: string) => {
        return nodeTypes.value.filter(n => n.category === category)
    }

    const getNodeType = (type: string) => {
        return nodeTypes.value.find(n => n.type === type)
    }

    // Actions
    async function fetchNodeTypes() {
        if (isLoadingNodeTypes.value) return

        try {
            isLoadingNodeTypes.value = true
            const res = await getNodeTypes()
            nodeTypes.value = res.node_types
        } catch (error) {
            console.error('Failed to fetch node types:', error)
        } finally {
            isLoadingNodeTypes.value = false
        }
    }

    async function fetchCardTypes() {
        if (cardTypes.value.length > 0) return // cache
        try {
            const { getCardTypes } = await import('../api/cards')
            cardTypes.value = await getCardTypes()
        } catch (error) {
            console.error('Failed to fetch card types:', error)
        }
    }

    // ==================== 运行状态管理 ====================
    const runs = ref<Map<number, RunInfo>>(new Map())
    const pollingTimer = ref<any>(null)
    const sseConnections = ref<Map<number, SSEConnection>>(new Map()) // 管理所有 SSE 连接

    // Getters
    const activeRuns = computed(() => {
        return Array.from(runs.value.values()).filter(r =>
            ['pending', 'running', 'paused'].includes(r.status)
        ).sort((a, b) => b.id - a.id)
    })

    const completedRuns = computed(() => {
        return Array.from(runs.value.values()).filter(r =>
            ['succeeded', 'failed', 'cancelled', 'timeout'].includes(r.status)
        ).sort((a, b) => b.id - a.id)
    })

    const totalRunCount = computed(() => runs.value.size)
    const activeRunCount = computed(() => activeRuns.value.length)

    // Actions
    function addRun(id: number, workflowName?: string) {
        if (runs.value.has(id)) return

        // 初始化占位
        runs.value.set(id, {
            id,
            workflow_id: 0,
            status: 'running',
            workflow_name: workflowName || '加载中...',
            progress: 0
        })

        // 立即获取一次详情
        fetchRunDetails(id)

        // 确保轮询开启
        startPolling()
    }

    function updateRunProgress(id: number, progress: number, currentNode?: string) {
        const run = runs.value.get(id)
        if (run) {
            runs.value.set(id, {
                ...run,
                progress,
                current_node: currentNode
            })
        }
    }

    function updateRunStatus(id: number, status: string, error?: string) {
        const run = runs.value.get(id)
        if (run) {
            runs.value.set(id, {
                ...run,
                status,
                error
            })
        }
    }

    async function fetchRunDetails(id: number) {
        try {
            const run = await getRun(id)
            if (run) {
                const existingRun = runs.value.get(id)
                
                // 从 error_json 提取错误信息
                let errorMessage: string | undefined
                if (run.error_json) {
                    errorMessage = typeof run.error_json === 'object' 
                        ? JSON.stringify(run.error_json) 
                        : String(run.error_json)
                }
                
                runs.value.set(id, {
                    id: run.id,
                    workflow_id: run.workflow_id,
                    workflow_name: run.workflow?.name || '未命名工作流',
                    status: run.status,
                    created_at: run.created_at || undefined,
                    error: errorMessage,
                    current_node: existingRun?.current_node, // 保留当前节点信息
                    progress: existingRun?.progress // 保留进度信息
                })
            }
        } catch (e) {
            console.error(`Failed to fetch run ${id}`, e)
        }
    }

    function startPolling() {
        if (pollingTimer.value) return

        // 立即执行一次检查
        checkActiveRuns()

        pollingTimer.value = setInterval(() => {
            checkActiveRuns()
        }, 2000) // 2秒轮询一次
    }

    function stopPolling() {
        if (pollingTimer.value) {
            clearInterval(pollingTimer.value)
            pollingTimer.value = null
        }
    }

    /**
     * 监听后端触发的工作流（通过响应头通知）
     */
    function setupWorkflowListener() {
        const handleWorkflowStarted = (event: CustomEvent) => {
            const runIds = event.detail as number[]
            
            // 添加所有新启动的运行到状态
            runIds.forEach(runId => {
                if (!runs.value.has(runId)) {
                    addRun(runId, '触发器工作流')
                }
            })
        }
        
        window.addEventListener('workflow-started', handleWorkflowStarted as EventListener)
        
        // 返回清理函数
        return () => {
            window.removeEventListener('workflow-started', handleWorkflowStarted as EventListener)
        }
    }

    async function checkActiveRuns() {
        if (activeRuns.value.length === 0) {
            stopPolling()
            return
        }

        // 更新所有活动运行的状态
        for (const run of activeRuns.value) {
            await fetchRunDetails(run.id)
        }
    }

    // 清理已完成的运行（可选，避免内存占用过多）
    function clearCompleted() {
        const completedIds = completedRuns.value.map(r => r.id)
        completedIds.forEach(id => {
            runs.value.delete(id)
            // 同时清理对应的 SSE 连接
            const conn = sseConnections.value.get(id)
            if (conn) {
                conn.eventSource.close()
                sseConnections.value.delete(id)
            }
        })
    }

    /**
     * 启动工作流执行（全局 SSE 连接管理）
     * @param workflowId 工作流 ID
     * @param workflowName 工作流名称
     * @param callbacks 回调函数（用于更新 UI）
     * @param resume 是否恢复执行
     * @param runId 恢复执行时的 run ID
     */
    async function startWorkflowExecution(
        workflowId: number,
        workflowName: string,
        callbacks: WorkflowStreamCallbacks,
        resume: boolean = false,
        runId?: number
    ) {
        let currentRunId: number | null = runId || null
        let totalNodes = 0
        let completedNodes = 0

        // 如果是恢复执行，确保运行记录存在且状态正确
        if (resume && runId) {
            const existingRun = runs.value.get(runId)
            if (existingRun) {
                // 更新状态为运行中
                updateRunStatus(runId, 'running')
                console.log('[WorkflowStore] 恢复执行，更新状态为 running:', runId)
            } else {
                // 如果不存在，添加到状态栏
                addRun(runId, workflowName)
                console.log('[WorkflowStore] 恢复执行，添加运行记录:', runId)
            }
        }

        // 包装回调，自动更新状态栏
        const wrappedCallbacks: WorkflowStreamCallbacks = {
            onRunStarted: (actualRunId: number) => {
                currentRunId = actualRunId
                // 添加到状态栏（仅新执行）
                if (!resume) {
                    addRun(actualRunId, workflowName)
                }
                // 调用原始回调
                if (callbacks.onRunStarted) {
                    callbacks.onRunStarted(actualRunId)
                }
            },

            onStart: (event) => {
                totalNodes++
                // 更新状态栏：当前节点
                if (currentRunId) {
                    const progress = totalNodes > 0 ? (completedNodes / totalNodes) * 100 : 0
                    updateRunProgress(currentRunId, progress, event.statement?.variable)
                }
                // 调用原始回调
                if (callbacks.onStart) {
                    callbacks.onStart(event)
                }
            },

            onProgress: (event) => {
                // 更新状态栏：进度
                if (currentRunId) {
                    const nodeProgress = event.percent || 0
                    const overallProgress = totalNodes > 0 
                        ? ((completedNodes + nodeProgress / 100) / totalNodes) * 100 
                        : nodeProgress
                    updateRunProgress(currentRunId, overallProgress, event.statement?.variable)
                }
                // 调用原始回调
                if (callbacks.onProgress) {
                    callbacks.onProgress(event)
                }
            },

            onComplete: (event) => {
                completedNodes++
                // 更新状态栏：完成一个节点
                if (currentRunId) {
                    const progress = totalNodes > 0 ? (completedNodes / totalNodes) * 100 : 100
                    updateRunProgress(currentRunId, progress, event.statement?.variable)
                }
                // 调用原始回调
                if (callbacks.onComplete) {
                    callbacks.onComplete(event)
                }
            },

            onError: (event) => {
                // 更新状态
                if (currentRunId) {
                    updateRunStatus(currentRunId, 'failed', event.error)
                }
                // 调用原始回调
                if (callbacks.onError) {
                    callbacks.onError(event)
                }
            },

            onEnd: () => {
                // 工作流结束，最终更新状态
                if (currentRunId) {
                    updateRunProgress(currentRunId, 100, undefined)
                    // 更新状态为 succeeded（如果不是 failed）
                    const run = runs.value.get(currentRunId)
                    if (run && run.status !== 'failed') {
                        updateRunStatus(currentRunId, 'succeeded')
                    }
                    // 清理 SSE 连接
                    const conn = sseConnections.value.get(currentRunId)
                    if (conn) {
                        conn.eventSource.close()
                        sseConnections.value.delete(currentRunId)
                    }
                }
                // 调用原始回调
                if (callbacks.onEnd) {
                    callbacks.onEnd()
                }
            }
        }

        try {
            // 如果是恢复执行，先清理旧的 SSE 连接
            if (resume && runId) {
                const oldConn = sseConnections.value.get(runId)
                if (oldConn) {
                    console.log('[WorkflowStore] 清理旧的 SSE 连接:', runId)
                    oldConn.eventSource.close()
                    sseConnections.value.delete(runId)
                }
            }
            
            // 启动 SSE 连接
            const { runId: actualRunId, eventSource } = await runCodeWorkflowStream(
                workflowId,
                wrappedCallbacks,
                resume,
                runId
            )

            // 保存连接信息
            if (currentRunId) {
                console.log('[WorkflowStore] 保存 SSE 连接:', currentRunId)
                sseConnections.value.set(currentRunId, {
                    runId: currentRunId,
                    workflowId,
                    workflowName,
                    eventSource,
                    callbacks: wrappedCallbacks
                })
            }

            return { runId: actualRunId, eventSource }
        } catch (error) {
            console.error('[WorkflowStore] 启动工作流失败:', error)
            throw error
        }
    }

    /**
     * 暂停工作流执行
     */
    function pauseWorkflowExecution(runId: number) {
        console.log('[WorkflowStore] 暂停工作流执行:', runId)
        const conn = sseConnections.value.get(runId)
        if (conn) {
            console.log('[WorkflowStore] 关闭 SSE 连接:', runId)
            conn.eventSource.close()
            sseConnections.value.delete(runId)
            updateRunStatus(runId, 'paused')
        } else {
            console.warn('[WorkflowStore] 未找到 SSE 连接:', runId)
        }
    }

    /**
     * 获取 SSE 连接
     */
    function getSSEConnection(runId: number) {
        return sseConnections.value.get(runId)
    }

    return {
        // 元数据
        nodeTypes,
        cardTypes,
        isLoadingNodeTypes,
        categories,
        getNodesByCategory,
        getNodeType,
        fetchNodeTypes,
        fetchCardTypes,
        
        // 运行状态
        runs,
        activeRuns,
        completedRuns,
        activeRunCount,
        totalRunCount,
        addRun,
        updateRunProgress,
        updateRunStatus,
        clearCompleted,
        startWorkflowExecution,
        pauseWorkflowExecution,
        getSSEConnection,
        
        // 工作流监听器
        setupWorkflowListener
    }
})
