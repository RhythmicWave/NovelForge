
import { defineStore } from 'pinia'
import { ref, computed, onUnmounted } from 'vue'
import { getRun, type WorkflowRunRead } from '@/api/workflows'

// 简单的运行信息接口，用于状态栏显示
export interface RunInfo {
    id: number
    workflow_id: number
    workflow_name?: string
    status: string
    created_at?: string
    duration?: number
    error?: string
}

export const useWorkflowStatusStore = defineStore('workflow-status', () => {
    const runs = ref<Map<number, RunInfo>>(new Map())
    const pollingTimer = ref<any>(null)

    // Getters
    const activeRuns = computed(() => {
        return Array.from(runs.value.values()).filter(r =>
            ['pending', 'running'].includes(r.status)
        ).sort((a, b) => b.id - a.id)
    })

    const completedRuns = computed(() => {
        return Array.from(runs.value.values()).filter(r =>
            ['succeeded', 'failed', 'cancelled', 'timeout'].includes(r.status)
        ).sort((a, b) => b.id - a.id)
    })

    const totalCount = computed(() => runs.value.size)
    const activeCount = computed(() => activeRuns.value.length)

    // Actions
    function addRun(id: number) {
        if (runs.value.has(id)) return

        // 初始化占位
        runs.value.set(id, {
            id,
            workflow_id: 0,
            status: 'running',
            workflow_name: '加载中...'
        })

        // 立即获取一次详情
        fetchRunDetails(id)

        // 确保轮询开启
        startPolling()
    }

    async function fetchRunDetails(id: number) {
        try {
            const run = await getRun(id)
            if (run) {
                runs.value.set(id, {
                    id: run.id,
                    workflow_id: run.workflow_id,
                    workflow_name: run.workflow?.name || '未命名工作流',
                    status: run.status,
                    created_at: run.created_at,
                    duration: run.duration,
                    error: run.error
                })
            }
        } catch (e) {
            console.error(`Failed to fetch run ${id}`, e)
            // 如果404，可能已被清理，标记为未知或移除
            if (runs.value.has(id)) {
                const r = runs.value.get(id)!
                // 如果很久都没刷出来，可能要移除，暂时保留
            }
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

    async function checkActiveRuns() {
        if (activeRuns.value.length === 0) {
            // 只要没有活动的，就停止轮询以节省资源
            // 但是为了防止新加入的，我们保持 listener
            // 这里可以放宽策略：如果没有活动的，降频？或者停止，依靠 addRun 重新唤醒
            stopPolling()
            return
        }

        // 更新所有活动运行的状态
        for (const run of activeRuns.value) {
            await fetchRunDetails(run.id)
        }
    }

    // 初始化监听
    function init() {
        window.addEventListener('workflow-started', ((e: CustomEvent) => {
            const ids = e.detail as number[]
            if (ids && Array.isArray(ids)) {
                ids.forEach(id => addRun(id))
            }
        }) as EventListener)
    }

    return {
        runs,
        activeRuns,
        completedRuns,
        activeCount,
        totalCount,
        addRun,
        init
    }
})
