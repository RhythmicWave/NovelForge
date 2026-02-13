<template>
  <el-dialog
    v-model="visible"
    title="工作流运行记录"
    width="90%"
    :close-on-click-modal="false"
  >
    <div class="runs-dialog-content">
      <!-- 过滤器 -->
      <div class="filters">
        <el-select v-model="statusFilter" placeholder="状态筛选" clearable @change="loadRuns" style="width: 150px">
          <el-option label="全部" value="" />
          <el-option label="运行中" value="running" />
          <el-option label="已暂停" value="paused" />
          <el-option label="已完成" value="succeeded" />
          <el-option label="失败" value="failed" />
        </el-select>
        <el-button @click="loadRuns" :icon="Refresh">刷新</el-button>
      </div>

      <!-- 运行列表 -->
      <el-table :data="runs" v-loading="loading" stripe style="margin-top: 10px">
        <el-table-column prop="id" label="ID" width="60" />
        
        <el-table-column label="工作流" width="180">
          <template #default="{ row }">
            {{ row.workflow?.name || `工作流 #${row.workflow_id}` }}
          </template>
        </el-table-column>

        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)" size="small">
              {{ getStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="进度" width="150">
          <template #default="{ row }">
            <el-progress 
              v-if="row.status === 'running' || row.status === 'paused'"
              :percentage="getProgress(row.id)" 
              :status="row.status === 'paused' ? 'warning' : undefined"
              :stroke-width="8"
            />
            <el-progress 
              v-else-if="row.status === 'succeeded'"
              :percentage="100" 
              status="success"
              :stroke-width="8"
            />
            <el-progress 
              v-else-if="row.status === 'failed'"
              :percentage="100" 
              status="exception"
              :stroke-width="8"
            />
          </template>
        </el-table-column>

        <el-table-column label="创建时间" width="160">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>

        <el-table-column label="操作" fixed="right" width="320">
          <template #default="{ row }">
            <div style="display: flex; gap: 4px; flex-wrap: nowrap;">
              <el-button
                v-if="row.status === 'running'"
                @click="pauseRun(row.id)"
                :icon="VideoPause"
                size="small"
              >
                暂停
              </el-button>

              <el-button
                v-if="row.status === 'paused' || row.status === 'failed'"
                type="primary"
                @click="resumeRunFromDialog(row)"
                :icon="VideoPlay"
                size="small"
              >
                恢复
              </el-button>

              <el-button
                @click="viewNodeStatus(row.id)"
                :icon="List"
                size="small"
              >
                状态
              </el-button>
              
              <el-button
                type="danger"
                @click="deleteRun(row.id)"
                :icon="Delete"
                plain
                size="small"
              >
                删除
              </el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 节点状态对话框 -->
    <el-dialog
      v-model="nodeStatusVisible"
      title="节点执行状态"
      width="700px"
      append-to-body
    >
      <el-table :data="nodeStatuses" v-loading="loadingNodeStatus" size="small">
        <el-table-column prop="node_id" label="节点 ID" width="120" />
        <el-table-column prop="node_type" label="节点类型" width="150" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)" size="small">
              {{ getStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="进度" width="120">
          <template #default="{ row }">
            <el-progress :percentage="row.progress" :stroke-width="6" />
          </template>
        </el-table-column>
        <el-table-column prop="error" label="错误" show-overflow-tooltip />
      </el-table>
    </el-dialog>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, VideoPause, VideoPlay, Close, List, Delete } from '@element-plus/icons-vue'
import { deleteRun as deleteRunApi } from '@renderer/api/workflows'
import request from '@renderer/api/request'

interface WorkflowRun {
  id: number
  workflow_id: number
  status: string
  created_at: string
  workflow?: {
    id: number
    name: string
  }
}

interface NodeStatus {
  node_id: string
  node_type: string
  status: string
  progress: number
  error?: string
}

interface RunStatusResponse {
  nodes: NodeStatus[]
}

const props = defineProps<{
  modelValue: boolean
  workflowId?: number
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'resume-run', run: WorkflowRun): void
}>()

const visible = ref(props.modelValue)
const runs = ref<WorkflowRun[]>([])
const loading = ref(false)
const statusFilter = ref('')
const progressCache = ref<Record<number, number>>({})

const nodeStatusVisible = ref(false)
const nodeStatuses = ref<NodeStatus[]>([])
const loadingNodeStatus = ref(false)

let refreshTimer: number | null = null

watch(() => props.modelValue, (val) => {
  visible.value = val
  if (val) {
    loadRuns()
    startAutoRefresh()
  } else {
    stopAutoRefresh()
  }
})

watch(visible, (val) => {
  emit('update:modelValue', val)
  if (!val) {
    stopAutoRefresh()
  }
})

onUnmounted(() => {
  stopAutoRefresh()
})

function startAutoRefresh() {
  stopAutoRefresh()
  refreshTimer = window.setInterval(() => {
    if (runs.value.some(r => r.status === 'running' || r.status === 'paused')) {
      loadRuns(true)
    }
  }, 3000)
}

function stopAutoRefresh() {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

async function loadRuns(silent = false) {
  if (!silent) {
    loading.value = true
  }

  try {
    const params: any = { limit: 50, offset: 0 }
    if (statusFilter.value) {
      params.status = statusFilter.value
    }

    // 如果指定了 workflowId，只加载该工作流的运行记录
    const url = props.workflowId 
      ? `/workflows/${props.workflowId}/runs`
      : '/runs'
    
    const response = await request.get<WorkflowRun[]>(url, params, '/api')
    runs.value = response

    // 加载运行中任务的进度
    for (const run of runs.value) {
      if (run.status === 'running' || run.status === 'paused') {
        loadProgress(run.id)
      }
    }
  } catch (error: any) {
    if (!silent) {
      ElMessage.error(`加载运行列表失败：${error.message || error}`)
    }
  } finally {
    if (!silent) {
      loading.value = false
    }
  }
}

async function loadProgress(runId: number) {
  try {
    const status = await request.get<RunStatusResponse>(
      `/workflows/runs/${runId}/status`,
      {},
      '/api',
      { showLoading: false }
    )
    
    if (status.nodes && status.nodes.length > 0) {
      const totalProgress = status.nodes.reduce((sum: number, node: NodeStatus) => {
        return sum + node.progress
      }, 0)
      progressCache.value[runId] = Math.round(totalProgress / status.nodes.length)
    }
  } catch (error) {
    // 静默失败，避免干扰用户
    console.warn(`[WorkflowRunsDialog] 加载进度失败: runId=${runId}`, error)
  }
}

function getProgress(runId: number): number {
  return progressCache.value[runId] || 0
}

async function pauseRun(runId: number) {
  try {
    await request.post(`/workflows/runs/${runId}/pause`, {}, '/api')
    ElMessage.success('工作流已暂停')
    loadRuns()
  } catch (error: any) {
    ElMessage.error(`暂停失败：${error.message || error}`)
  }
}

async function resumeRun(runId: number) {
  try {
    await request.post(`/workflows/runs/${runId}/resume`, {}, '/api')
    ElMessage.success('工作流已恢复，将从断点继续执行')
    loadRuns()
  } catch (error: any) {
    ElMessage.error(`恢复失败：${error.message || error}`)
  }
}

async function resumeRunFromDialog(run: WorkflowRun) {
  try {
    // 关闭对话框
    visible.value = false
    
    // 通知父组件恢复执行
    emit('resume-run', run)
    
    ElMessage.success('正在恢复工作流执行...')
  } catch (error: any) {
    ElMessage.error(`恢复失败：${error.message || error}`)
  }
}

async function cancelRun(runId: number) {
  try {
    await ElMessageBox.confirm('确定要取消这个工作流运行吗？', '确认取消', {
      type: 'warning'
    })

    await request.post(`/workflows/runs/${runId}/cancel`, {}, '/api')
    ElMessage.success('工作流已取消')
    loadRuns()
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(`取消失败：${error.message || error}`)
    }
  }
}

async function viewNodeStatus(runId: number) {
  nodeStatusVisible.value = true
  loadingNodeStatus.value = true

  try {
    const status = await request.get<RunStatusResponse>(`/workflows/runs/${runId}/status`, {}, '/api')
    nodeStatuses.value = status.nodes || []
  } catch (error: any) {
    ElMessage.error(`加载节点状态失败：${error.message || error}`)
  } finally {
    loadingNodeStatus.value = false
  }
}

async function deleteRun(runId: number) {
  try {
    await ElMessageBox.confirm('确定要删除这条运行记录吗？此操作不可恢复。', '确认删除', {
      type: 'warning',
      confirmButtonText: '确定删除',
      cancelButtonText: '取消'
    })

    await deleteRunApi(runId)
    ElMessage.success('运行记录已删除')
    loadRuns()
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(`删除失败：${error.message || error}`)
    }
  }
}

function getStatusType(status: string): string {
  const typeMap: Record<string, string> = {
    running: 'primary',
    paused: 'warning',
    succeeded: 'success',
    failed: 'danger',
    cancelled: 'info',
    idle: 'info',
    pending: 'info',
    success: 'success',
    error: 'danger'
  }
  return typeMap[status] || 'info'
}

function getStatusLabel(status: string): string {
  const labelMap: Record<string, string> = {
    running: '运行中',
    paused: '已暂停',
    succeeded: '已完成',
    failed: '失败',
    cancelled: '已取消',
    idle: '空闲',
    pending: '等待中',
    success: '成功',
    error: '错误',
    skipped: '已跳过'
  }
  return labelMap[status] || status
}

function formatTime(time?: string | number): string {
  if (!time) return '-'
  
  // 如果是数字（Unix 时间戳），需要乘以 1000 转换为毫秒
  // 但如果数字很小（< 100000000），说明可能是错误的数据
  if (typeof time === 'number') {
    console.warn('[formatTime] 收到数字类型的时间戳:', time)
    if (time < 100000000) {
      console.error('[formatTime] 时间戳异常小，可能是错误数据')
      return '数据异常'
    }
    time = time * 1000 // 转换为毫秒
  }
  
  const date = new Date(time)
  
  // 检查日期是否有效
  if (isNaN(date.getTime())) {
    console.error('[formatTime] 无效的日期:', time)
    return '无效日期'
  }
  
  // 检查日期是否在合理范围内（2020-2030）
  const year = date.getFullYear()
  if (year < 2020 || year > 2030) {
    console.error('[formatTime] 日期超出合理范围:', date.toISOString(), '原始值:', time)
    return '日期异常'
  }
  
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}
</script>

<style scoped>
.runs-dialog-content {
  min-height: 400px;
}

.filters {
  display: flex;
  gap: 10px;
  margin-bottom: 10px;
}
</style>
