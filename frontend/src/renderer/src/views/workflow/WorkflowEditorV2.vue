<template>
  <div class="workflow-editor">
    <!-- 顶部工具栏 -->
    <div class="editor-header">
      <div class="header-left">
        <el-select
          v-model="currentWorkflowId"
          placeholder="选择工作流"
          class="workflow-selector"
          filterable
          @change="handleWorkflowChange"
        >
          <el-option
            v-for="wf in workflowList"
            :key="wf.id"
            :value="wf.id"
            :label="wf.name"
          />
        </el-select>
        <el-button @click="handleNewWorkflow" :icon="Plus">
          新建
        </el-button>
        <el-button 
          @click="handleDeleteWorkflow" 
          :icon="Delete" 
          :disabled="!currentWorkflowId"
          type="danger"
          plain
        >
          删除
        </el-button>
      </div>
      <div class="header-actions">
        <el-switch
          v-model="keepRunHistory"
          active-text="持久化保存"
          style="margin-right: 15px; --el-switch-on-color: #13ce66"
        />
        <el-button @click="handleSave" type="primary" :loading="saving" :disabled="!currentWorkflowId">
          <el-icon><DocumentCopy /></el-icon>
          保存
        </el-button>
        <el-button @click="handleRun" type="success" :loading="running">
          <el-icon><VideoPlay /></el-icon>
          运行
        </el-button>
        
        <el-dropdown trigger="click" style="margin-left: 12px">
          <el-button :icon="MoreFilled" circle />
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item :icon="CircleCheck" @click="handleValidate">验证工作流</el-dropdown-item>
              <el-dropdown-item :icon="Upload" @click="handleImportClick" divided>导入...</el-dropdown-item>
              <el-dropdown-item :icon="Download" @click="handleExport">导出...</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <input
          ref="fileInput"
          type="file"
          accept=".json"
          style="display: none"
          @change="handleImportFile"
        />
      </div>
    </div>

    <!-- 主内容区：三栏布局 -->
    <div class="editor-body">
      <!-- 左侧：节点库面板 -->
      <div class="left-panel">
        <NodeLibrary @add-node="handleAddNode" />
      </div>

      <!-- 中间画布区 -->
      <div class="editor-canvas">
        <WorkflowCanvas
          :nodes="nodes"
          :edges="edges"
          :selected-node-id="selectedNodeId"
          @update:nodes="nodes = $event"
          @update:edges="edges = $event"
          @node-click="handleNodeClick"
          @edge-click="handleEdgeClick"
          @pane-click="handlePaneClick"
          @add-node="handleShowQuickMenu"
        />
      </div>
      
      <!-- 快捷菜单 -->
      <NodeQuickMenu
        :visible="quickMenuVisible"
        :position="quickMenuPosition"
        @select="handleQuickMenuSelect"
        @close="quickMenuVisible = false"
      />

      <!-- 右侧：属性/调试面板 -->
      <div class="right-panel">
        <PropertyPanel
          :selected-node="selectedNode"
          :selected-edge="selectedEdge"
          :edges="edges"
          :run-status="runStatus"
          @update-node="handleUpdateNode"
          @delete-node="handleDeleteNode"
        />
      </div>
    </div>

    <!-- 底部状态栏 -->
    <div class="editor-footer">
      <StatusBar :nodes="nodes" :run-status="runStatus" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, onBeforeUnmount, provide } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CircleCheck, DocumentCopy, VideoPlay, Download, Plus, Delete, Upload, MoreFilled } from '@element-plus/icons-vue'
import NodeLibrary from '@/components/workflow-v2/panels/NodeLibrary.vue'
import WorkflowCanvas from '@/components/workflow-v2/canvas/WorkflowCanvas.vue'
import PropertyPanel from '@/components/workflow-v2/panels/PropertyPanel.vue'
import StatusBar from '@/components/workflow-v2/panels/StatusBar.vue'
import NodeQuickMenu from '@/components/workflow-v2/canvas/NodeQuickMenu.vue'
import { getWorkflow, createWorkflow, updateWorkflow, validateWorkflow, listWorkflows, deleteWorkflow, runWorkflow, getRunStatus, connectRunEvents, type WorkflowRead, type NodeExecutionStatus } from '@/api/workflows'
import { MarkerType } from '@vue-flow/core'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'

// Props
const props = defineProps<{
  workflowId?: number
}>()

// 工作流基本信息
const workflowName = ref('新建工作流')
const workflowDescription = ref('')
const keepRunHistory = ref(false)
const currentWorkflowId = ref<number | undefined>(props.workflowId)
const workflowList = ref<WorkflowRead[]>([])
const currentRunId = ref<number | undefined>()
const nodeStates = ref<Map<string, NodeExecutionStatus>>(new Map())
const statusPollingInterval = ref<number | undefined>()
const sseConnection = ref<EventSource | null>(null)
const sseConnected = ref(false)
const lastEventTime = ref<number>(0)
const triggerDialogVisible = ref(false)

const nodes = ref<any[]>([
  {
    id: '1',
    type: 'Logic.Start',
    position: { x: 100, y: 150 },
    data: { label: '开始', description: '工作流起点' }
  },
  {
    id: '2',
    type: 'Logic.SetVariable',
    position: { x: 350, y: 150 },
    data: { 
      label: '设置变量', 
      description: '设置用户名',
      config: {
        variableName: 'userName',
        value: 'Alice'
      }
    }
  },
  {
    id: '3',
    type: 'Logic.Condition',
    position: { x: 600, y: 150 },
    data: { 
      label: '条件分支', 
      description: '判断年龄',
      config: {
        condition: 'age > 18'
      },
      onAddNode: (nodeId: string, handleId: string, event: MouseEvent) => {
        handleShowQuickMenu({ nodeId, handleId, event })
      }
    }
  }
])
const edges = ref<any[]>([
  { id: 'e1-2', source: '1', target: '2', animated: true },
  { id: 'e2-3', source: '2', target: '3', animated: true }
])

// 选中状态
const selectedNodeId = ref<string | null>(null)
const selectedEdgeId = ref<string | null>(null)

// 计算选中的节点和边
const selectedNode = computed(() => {
  if (!selectedNodeId.value) return null
  return nodes.value.find(n => n.id === selectedNodeId.value)
})

const selectedEdge = computed(() => {
  if (!selectedEdgeId.value) return null
  return edges.value.find(e => e.id === selectedEdgeId.value)
})

// 运行状态
const runStatus = ref<any>(null)

// 提供 runStatus 给子组件（如 DisplayNode）
provide('runStatus', runStatus)

// 加载状态
const saving = ref(false)
const validating = ref(false)
const running = ref(false)

// 撤销/重做历史
const history = ref<Array<{ nodes: any[], edges: any[] }>>([])
const historyIndex = ref(-1)
const maxHistorySize = 50

// 保存当前状态到历史
const saveToHistory = () => {
  // 移除当前索引之后的所有历史
  if (historyIndex.value < history.value.length - 1) {
    history.value = history.value.slice(0, historyIndex.value + 1)
  }
  
  // 添加新状态
  history.value.push({
    nodes: JSON.parse(JSON.stringify(nodes.value)),
    edges: JSON.parse(JSON.stringify(edges.value))
  })
  
  // 限制历史大小
  if (history.value.length > maxHistorySize) {
    history.value.shift()
  } else {
    historyIndex.value++
  }
}

// 撤销
const undo = () => {
  if (historyIndex.value > 0) {
    historyIndex.value--
    const state = history.value[historyIndex.value]
    nodes.value = JSON.parse(JSON.stringify(state.nodes))
    edges.value = JSON.parse(JSON.stringify(state.edges))
  }
}

// 重做
const redo = () => {
  if (historyIndex.value < history.value.length - 1) {
    historyIndex.value++
    const state = history.value[historyIndex.value]
    nodes.value = JSON.parse(JSON.stringify(state.nodes))
    edges.value = JSON.parse(JSON.stringify(state.edges))
  }
}

// 监听键盘快捷键
const handleKeyDown = (event: KeyboardEvent) => {
  if ((event.ctrlKey || event.metaKey) && event.key === 'z') {
    if (event.shiftKey) {
      // Ctrl+Shift+Z 重做
      redo()
    } else {
      // Ctrl+Z 撤销
      undo()
    }
    event.preventDefault()
  }
}

// 监听节点和边的变化，保存到历史
watch([nodes, edges], () => {
  saveToHistory()
}, { deep: true })

// 快捷菜单状态
const quickMenuVisible = ref(false)
const quickMenuPosition = ref({ x: 0, y: 0 })
const quickMenuSourceNodeId = ref<string | null>(null)
const quickMenuSourceHandleId = ref<string | null>(null)

// 显示快捷菜单
const handleShowQuickMenu = ({ nodeId, handleId, event }: { nodeId: string; handleId?: string; event: MouseEvent }) => {
  quickMenuSourceNodeId.value = nodeId
  quickMenuSourceHandleId.value = handleId || null
  quickMenuPosition.value = {
    x: event.clientX + 20,
    y: event.clientY - 20
  }
  quickMenuVisible.value = true
}

// 快捷菜单选择节点
const handleQuickMenuSelect = (nodeType: string) => {
  if (!quickMenuSourceNodeId.value) return
  
  const sourceNode = nodes.value.find(n => n.id === quickMenuSourceNodeId.value)
  if (!sourceNode) return
  
  // 创建新节点
  const newNodeId = `node-${Date.now()}`
  const nodeData: any = {
    label: nodeType.split('.')[1] || nodeType,
    description: '新节点',
    config: {}
  }
  
  // 如果是条件节点，添加 onAddNode 回调
  if (nodeType === 'Logic.Condition') {
    nodeData.onAddNode = (nodeId: string, handleId: string, event: MouseEvent) => {
      handleShowQuickMenu({ nodeId, handleId, event })
    }
  }
  
  const newNode = {
    id: newNodeId,
    type: nodeType,
    position: {
      x: sourceNode.position.x + 300,
      y: sourceNode.position.y
    },
    data: nodeData
  }
  
  nodes.value.push(newNode)
  
  // 创建连接
  const edgeStyle = { strokeWidth: 2, stroke: '#409eff' }
  let edgeLabel = ''
  let labelBgColor = '#409eff'
  
  if (quickMenuSourceHandleId.value === 'true') {
    edgeStyle.stroke = '#67c23a'
    edgeLabel = 'True'
    labelBgColor = '#67c23a'
  } else if (quickMenuSourceHandleId.value === 'false') {
    edgeStyle.stroke = '#f56c6c'
    edgeLabel = 'False'
    labelBgColor = '#f56c6c'
  }
  
  const newEdge: any = {
    id: `edge-${Date.now()}`,
    source: quickMenuSourceNodeId.value,
    sourceHandle: quickMenuSourceHandleId.value,
    target: newNodeId,
    animated: true,
    style: edgeStyle,
    markerEnd: MarkerType.ArrowClosed
  }
  
  // 只有条件分支才添加标签
  if (edgeLabel) {
    newEdge.label = edgeLabel
    newEdge.labelStyle = { 
      fill: '#fff',
      fontWeight: 600,
      fontSize: 12
    }
    newEdge.labelBgStyle = { 
      fill: labelBgColor,
      fillOpacity: 0.9
    }
    newEdge.labelBgPadding = [4, 8]
    newEdge.labelBgBorderRadius = 4
  }
  
  edges.value.push(newEdge)
  
  quickMenuVisible.value = false
  
  // 添加节点和连接后清空运行状态
  clearRunStatus()
}

// 事件处理

const handleAddNode = (nodeType: string, position?: { x: number; y: number }) => {
  const newNode = {
    id: `node-${Date.now()}`,
    type: nodeType,
    position: position || { x: 100, y: 100 },
    data: {
      label: nodeType,
      config: {}
    }
  }
  nodes.value.push(newNode)
  // 添加节点后清空运行状态
  clearRunStatus()
}

const handleNodeClick = (nodeId: string) => {
  selectedNodeId.value = nodeId
  selectedEdgeId.value = null
}

const handleEdgeClick = (edgeId: string) => {
  selectedEdgeId.value = edgeId
  selectedNodeId.value = null
}

const handlePaneClick = () => {
  selectedNodeId.value = null
  selectedEdgeId.value = null
}

// 清空运行状态样式
const clearRunStatus = () => {
  console.log('[清空状态] 清空运行状态, 当前节点数:', nodeStates.value.size)
  nodeStates.value.clear()
  runStatus.value = null
  updateNodeStyles()
  console.log('[清空状态] 完成')
}

const handleUpdateNode = (nodeId: string, data: any) => {
  const node = nodes.value.find(n => n.id === nodeId)
  if (node) {
    node.data = { ...node.data, ...data }
  }
  // 修改节点配置后清空运行状态
  clearRunStatus()
}

const handleDeleteNode = (nodeId: string) => {
  nodes.value = nodes.value.filter(n => n.id !== nodeId)
  edges.value = edges.value.filter(e => e.source !== nodeId && e.target !== nodeId)
  selectedNodeId.value = null
  // 删除节点后清空运行状态
  clearRunStatus()
}

const handleValidate = async () => {
  validating.value = true
  try {
    if (!currentWorkflowId.value) {
      ElMessage.warning('请先保存工作流')
      return
    }
    
    const result = await validateWorkflow(currentWorkflowId.value)
    
    if (result.errors && result.errors.length > 0) {
      ElMessage.error(`验证失败: ${result.errors.join(', ')}`)
    } else {
      ElMessage.success('工作流验证通过')
    }
  } catch (error: any) {
    ElMessage.error(error.message || '验证失败')
  } finally {
    validating.value = false
  }
}

const handleSave = async (showMessage = true) => {
  saving.value = true
  try {
    // 构建工作流定义JSON
    const definition = {
      nodes: nodes.value.map(n => {
        // 从 edges 中收集该节点的依赖
        const dependencies = edges.value
          .filter(e => e.target === n.id && e.data?.isDependency)
          .map(e => e.source)
          
        return {
          id: n.id,
          type: n.type,
          label: n.data.label,
          position: n.position,
          config: n.data.config || {},
          // 保存依赖列表
          dependencies: dependencies.length > 0 ? dependencies : undefined
        }
      }),
      edges: edges.value
        .filter(e => !e.data?.isDependency) // 过滤掉依赖边
        .map(e => ({
          id: e.id,
          source: e.source,
          sourceHandle: e.sourceHandle,
          target: e.target,
          targetHandle: e.targetHandle,
          type: 'default',
          label: e.label,
          animated: e.animated,
          style: e.style,
          labelStyle: e.labelStyle,
          labelBgStyle: e.labelBgStyle,
          labelBgPadding: e.labelBgPadding,
          labelBgBorderRadius: e.labelBgBorderRadius
        })),
      variables: [],
      settings: {
        errorHandling: 'stop',
        logLevel: 'info'
      },
      keep_run_history: keepRunHistory.value
    }
    
    if (currentWorkflowId.value) {
      // 更新现有工作流
      await updateWorkflow(currentWorkflowId.value, {
        definition_json: definition,
        keep_run_history: keepRunHistory.value
      })
      if (showMessage) {
        ElMessage.success('保存成功')
      }
    } else {
      // 如果没有 ID，说明是新工作流，应该先通过"新建"按钮创建
      ElMessage.warning('请先通过"新建"按钮创建工作流')
      return
    }
  } catch (error: any) {
    if (showMessage) {
      ElMessage.error(error.message || '保存失败')
    }
    throw error
  } finally {
    saving.value = false
  }
}

const handleRun = async () => {
  if (!currentWorkflowId.value) {
    ElMessage.warning('请先选择工作流')
    return
  }
  
  // 清空之前的运行状态
  clearRunStatus()
  
  running.value = true
  
  try {
    // 先保存当前工作流
    await handleSave(false)
    
    // 启动工作流运行
    const run = await runWorkflow(currentWorkflowId.value, {
      scope_json: {},
      params_json: {}
    })
    
    // 验证返回数据
    if (!run || !run.id) {
      throw new Error('API 返回数据无效: ' + JSON.stringify(run))
    }
    
    currentRunId.value = run.id
    ElMessage.success(`工作流已启动 (Run ID: ${run.id})`)
    
    // 开始监控状态（SSE 优先 + 轮询兜底）
    startStatusMonitoring()
  } catch (error: any) {
    console.error('[运行] 启动失败:', error)
    ElMessage.error(error.message || '启动失败')
    running.value = false
  }
}

// 开始状态监控（SSE 优先 + 轮询兜底）
const startStatusMonitoring = () => {
  if (!currentRunId.value) {
    console.warn('[监控] currentRunId 为空，无法开始监控')
    return
  }
  
  // 1. 尝试 SSE 连接（会立即推送状态）
  connectSSE()
  
  // 2. 启动兜底轮询（3秒间隔，只在 SSE 失败或超时时生效）
  startFallbackPolling()
}

// 连接 SSE 事件流
const connectSSE = () => {
  if (!currentRunId.value) return
  
  try {
    // 使用封装好的 API 方法
    const eventSource = connectRunEvents(
      currentRunId.value,
      // onMessage
      (data) => {
        lastEventTime.value = Date.now()
        handleStatusUpdate(data)
      },
      // onError
      (error) => {
        console.error('[SSE] 连接错误')
        sseConnected.value = false
        if (sseConnection.value) {
          sseConnection.value.close()
          sseConnection.value = null
        }
        // SSE 失败，确保轮询兜底生效
      },
      // onOpen
      () => {
        sseConnected.value = true
        lastEventTime.value = Date.now()
      }
    )
    
    sseConnection.value = eventSource
  } catch (error) {
    console.error('[SSE] 创建连接失败:', error)
    sseConnected.value = false
  }
}

// 处理状态更新（SSE 和轮询共用）
const handleStatusUpdate = (status: any) => {
  // 保存完整的运行状态
  runStatus.value = status
  
  // 更新节点状态
  if (status.nodes && Array.isArray(status.nodes)) {
    const newStates = new Map<string, any>()
    status.nodes.forEach((node: any) => {
      if (node && node.node_id) {
        newStates.set(node.node_id, node)
      }
    })
    nodeStates.value = newStates
    updateNodeStyles()
  }
  
  // 检查是否完成
  if (status.status === 'succeeded' || status.status === 'failed' || status.status === 'cancelled') {
    stopStatusMonitoring()
    running.value = false
    
    if (status.status === 'succeeded') {
      ElMessage.success('工作流执行成功')
    } else if (status.status === 'failed') {
      ElMessage.error('工作流执行失败')
    } else {
      ElMessage.warning('工作流已取消')
    }
  }
}

// 兜底轮询（只在 SSE 失败或超时时生效）
const startFallbackPolling = () => {
  // 每 3 秒检查一次
  statusPollingInterval.value = window.setInterval(() => {
    // 如果 SSE 连接正常且最近 3 秒内有消息，不需要轮询
    if (sseConnected.value && lastEventTime.value > 0) {
      const now = Date.now()
      const timeSinceLastEvent = now - lastEventTime.value
      
      if (timeSinceLastEvent < 3000) {
        // SSE 正常工作，跳过轮询
        return
      }
      
    } else if (!sseConnected.value) {
    }
    
    // 执行轮询
    pollRunStatus()
  }, 3000)
}

// 停止状态监控
const stopStatusMonitoring = () => {
  // 关闭 SSE 连接
  if (sseConnection.value) {
    sseConnection.value.close()
    sseConnection.value = null
  }
  sseConnected.value = false
  
  // 停止轮询
  if (statusPollingInterval.value) {
    clearInterval(statusPollingInterval.value)
    statusPollingInterval.value = undefined
  }
}

// 开始轮询运行状态（已弃用，保留用于兜底）
const startStatusPolling = () => {
  if (!currentRunId.value) {
    console.warn('[轮询] currentRunId 为空，无法开始轮询')
    return
  }
  
  // 清除之前的轮询
  if (statusPollingInterval.value) {
    clearInterval(statusPollingInterval.value)
  }
  
  // 立即获取一次状态
  pollRunStatus()
  
  // 每秒轮询一次
  statusPollingInterval.value = window.setInterval(() => {
    pollRunStatus()
  }, 1000)
}

// 轮询运行状态（简化版，复用 handleStatusUpdate）
const pollRunStatus = async () => {
  if (!currentRunId.value) {
    console.warn('[轮询] currentRunId 为空')
    return
  }
  
  try {
    const status = await getRunStatus(currentRunId.value)
    
    if (!status || !status.status) {
      console.error('[轮询] 数据无效:', status)
      return
    }
    
    // 复用统一的状态更新逻辑
    handleStatusUpdate(status)
  } catch (error: any) {
    console.error('[轮询] 获取运行状态失败:', error)
  }
}

// 停止轮询
const stopStatusPolling = () => {
  if (statusPollingInterval.value) {
    clearInterval(statusPollingInterval.value)
    statusPollingInterval.value = undefined
  }
}

// 更新节点样式以反映执行状态
const updateNodeStyles = () => {
  nodes.value = nodes.value.map(node => {
    const state = nodeStates.value.get(node.id)
    
    // 如果没有状态，清除所有运行状态样式（恢复默认）
    if (!state) {
      return {
        ...node,
        style: {}  // 清空样式，恢复默认
      }
    }
    
    // 根据状态设置节点样式
    let style = {}
    switch (state.status) {
      case 'running':
        // 运行中：蓝色边框 + 发光效果
        style = { ...style, border: '2px solid #409eff', boxShadow: '0 0 10px rgba(64, 158, 255, 0.5)' }
        break
      case 'success':
        // 成功：绿色边框
        style = { ...style, border: '2px solid #67c23a' }
        break
      case 'error':
        // 失败：红色边框
        style = { ...style, border: '2px solid #f56c6c' }
        break
      case 'pending':
        // 等待中：橙色边框
        style = { ...style, border: '2px solid #e6a23c' }
        break
      case 'skipped':
        // 跳过：灰色边框 + 半透明
        style = { ...style, border: '2px dashed #909399', opacity: 0.6 }
        break
      case 'idle':
        // 空闲：不改变样式
        break
    }
    
    return {
      ...node,
      style,
      data: {
        ...node.data,
        executionState: state
      }
    }
  })
}

const handleExport = () => {
  // 使用与 handleSave 相同的逻辑构建标准 DSL
  const definition = {
    dsl_version: 1,
    name: workflowName.value,
    keep_run_history: keepRunHistory.value,
    nodes: nodes.value.map(n => {
      // 从 edges 中收集该节点的依赖
      const dependencies = edges.value
        .filter(e => e.target === n.id && e.data?.isDependency)
        .map(e => e.source)
        
      return {
        id: n.id,
        type: n.type,
        label: n.data.label,
        position: n.position,
        // 如果是触发器，使用 data 作为 data，如果是普通节点，使用 config
        // 但为了统一，我们尽量保持 config
        config: n.data.config || {},
        // 显式保留 data 中的 label, description 等
        data: {
            label: n.data.label,
            description: n.data.description
        },
        // 保存依赖列表
        dependencies: dependencies.length > 0 ? dependencies : undefined,
        // 兼容 params (虽然主要使用 config)
        params: n.data.params
      }
    }),
    edges: edges.value
      .filter(e => !e.data?.isDependency) // 过滤掉依赖边
      .map(e => ({
        id: e.id,
        source: e.source,
        sourceHandle: e.sourceHandle,
        target: e.target,
        targetHandle: e.targetHandle,
        type: 'default',
        label: e.label,
        animated: e.animated,
        // style: e.style, // DSL 不需要 style，前端加载时会重新计算
      }))
  }
  
  const blob = new Blob([JSON.stringify(definition, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${workflowName.value}.json`
  a.click()
  URL.revokeObjectURL(url)
}

// 导入功能
const fileInput = ref<HTMLInputElement | null>(null)

const handleImportClick = () => {
  fileInput.value?.click()
}

const handleImportFile = (event: Event) => {
  const target = event.target as HTMLInputElement
  if (!target.files || target.files.length === 0) return
  
  const file = target.files[0]
  const reader = new FileReader()
  
  reader.onload = (e) => {
    try {
      const content = e.target?.result as string
      const definition = JSON.parse(content)
      
      if (!definition.nodes || !Array.isArray(definition.nodes)) {
        throw new Error('无效的工作流文件格式：缺少 nodes 数组')
      }
      
      // 恢复持久化设置
      if (definition.keep_run_history !== undefined) {
        keepRunHistory.value = definition.keep_run_history
      } else {
        keepRunHistory.value = false
      }
      
      // 解析 nodes
      const newNodes = definition.nodes.map((n: any) => {
        return {
          id: n.id,
          type: n.type,
          position: n.position || { x: 0, y: 0 },
          data: {
            label: n.label || n.data?.label || n.type,
            description: n.data?.description || '',
            config: n.config || {},
            params: n.params || {}
          }
        }
      })
      
      // 解析 edges
      const newEdges: any[] = []
      
      // 1. 数据流边
      if (definition.edges && Array.isArray(definition.edges)) {
        definition.edges.forEach((e: any) => {
          newEdges.push({
            id: e.id,
            source: e.source,
            sourceHandle: e.sourceHandle || e.sourcePort,
            target: e.target,
            targetHandle: e.targetHandle || e.targetPort,
            type: 'default',
            animated: true,
            style: { strokeWidth: 2, stroke: '#409eff' },
            markerEnd: MarkerType.ArrowClosed
          })
        })
      }
      
      // 2. 依赖边 (从节点的 dependencies 字段恢复)
      definition.nodes.forEach((n: any) => {
        if (n.dependencies && Array.isArray(n.dependencies)) {
          n.dependencies.forEach((depSourceId: string) => {
             newEdges.push({
               id: `dep-${depSourceId}-${n.id}`,
               source: depSourceId,
               target: n.id,
               sourceHandle: 'dep-output',
               targetHandle: 'dep-input',
               type: 'default',
               animated: true,
               style: { strokeDasharray: '5,5', stroke: '#909399', opacity: 0.8 },
               data: { isDependency: true }
             })
          })
        }
      })
      
      // 更新画布
      nodes.value = newNodes
      edges.value = newEdges
      
      // 这里的 workflowName 只有在未保存时改名为导入的文件名，避免覆盖现有工作流名称
      if (!currentWorkflowId.value && definition.name) {
          workflowName.value = definition.name
      }
      
      ElMessage.success('导入成功')
      
    } catch (error: any) {
      ElMessage.error('导入失败: ' + error.message)
    } finally {
      // 清空 input 以便重复导入同名文件
      target.value = ''
    }
  }
  
  reader.readAsText(file)
}

// 加载工作流数据
const loadWorkflow = async () => {
  if (!currentWorkflowId.value) return
  
  try {
    const workflow = await getWorkflow(currentWorkflowId.value)
    
    // 恢复工作流名称和描述
    workflowName.value = workflow.name
    workflowDescription.value = workflow.description || ''
    keepRunHistory.value = workflow.keep_run_history || false
    
    // 恢复节点和边
    const definition = (workflow.definition_json || {}) as any
    const visualEdges: any[] = []
    
    // 1. 处理普通边
    if (definition.edges && definition.edges.length > 0) {
      definition.edges.forEach((e: any) => {
        visualEdges.push({
          id: e.id,
          source: e.source,
          sourceHandle: e.sourceHandle || e.sourcePort,  // 兼容两种命名
          target: e.target,
          targetHandle: e.targetHandle || e.targetPort,  // 兼容两种命名
          animated: e.animated,
          style: e.style,
          label: e.label,
          labelStyle: e.labelStyle,
          labelBgStyle: e.labelBgStyle,
          labelBgPadding: e.labelBgPadding || [4, 8],
          labelBgBorderRadius: e.labelBgBorderRadius || 4,
          markerEnd: e.markerEnd || MarkerType.ArrowClosed,
          data: { isDependency: false } // 标记为普通边
        })
      })
    }
    
    // 2. 处理节点和依赖
    if (definition.nodes && definition.nodes.length > 0) {
      nodes.value = definition.nodes.map((n: any) => {
        // 如果有显式依赖，生成虚线边
        if (n.dependencies && Array.isArray(n.dependencies)) {
          n.dependencies.forEach((depId: string) => {
            visualEdges.push({
              id: `dep-${depId}-${n.id}`,
              source: depId,
              sourceHandle: 'dep-output', // 明确指定端口
              target: n.id,
              targetHandle: 'dep-input',  // 明确指定端口
              animated: true,
              style: { strokeDasharray: '5,5', stroke: '#909399', opacity: 0.8 }, // 灰色虚线
              type: 'default',
              data: { isDependency: true }, // 标记为依赖边
              selectable: true
            })
          })
        }
        
        return {
          id: n.id,
          type: n.type,
          position: n.position,
          data: {
            label: n.label,
            config: n.config,
            // dependencies 只是暂存，实际由边维护
            dependencies: n.dependencies || [],
            // 条件节点需要添加 onAddNode 回调
            ...(n.type === 'Logic.Condition' ? {
              onAddNode: (nodeId: string, handleId: string, event: MouseEvent) => {
                handleShowQuickMenu({ nodeId, handleId, event })
              }
            } : {})
          }
        }
      })
    }
    
    edges.value = visualEdges
    
    // 清空历史并保存当前状态
    history.value = []
    historyIndex.value = -1
    saveToHistory()
    
    ElMessage.success('工作流加载成功')
  } catch (error: any) {
    ElMessage.error('加载工作流失败: ' + error.message)
  }
}

// 切换工作流
const handleWorkflowChange = async (workflowId: number | undefined) => {
  if (!workflowId) return
  
  // 加载选中的工作流
  await loadWorkflow()
}

// 新建工作流
const handleNewWorkflow = async () => {
  // 提示输入工作流名称
  const name = await ElMessageBox.prompt(
    '请输入工作流名称',
    '新建工作流',
    {
      confirmButtonText: '创建',
      cancelButtonText: '取消',
      inputPattern: /.+/,
      inputErrorMessage: '请输入工作流名称'
    }
  ).catch(() => null)
  
  if (!name || !name.value) return
  
  // 创建新工作流
  try {
    const definition = {
      nodes: [
        {
          id: '1',
          type: 'Logic.Start',
          label: '开始',
          position: { x: 100, y: 150 },
          config: {}
        }
      ],
      edges: [],
      variables: [],
      settings: {
        errorHandling: 'stop',
        logLevel: 'info'
      }
    }
    
    const result = await createWorkflow({
      name: name.value,
      description: '',
      definition_json: definition
    })
    
    // 重新加载工作流列表
    await loadWorkflowList()
    
    // 切换到新创建的工作流
    currentWorkflowId.value = result.id
    await loadWorkflow()
    
    ElMessage.success('工作流创建成功')
  } catch (error: any) {
    ElMessage.error('创建失败: ' + error.message)
  }
}

// 删除工作流
const handleDeleteWorkflow = async () => {
  if (!currentWorkflowId.value) return
  
  const confirmed = await ElMessageBox.confirm(
    '确定要删除这个工作流吗？此操作不可恢复！',
    '警告',
    {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'error'
    }
  ).catch(() => false)
  
  if (!confirmed) return
  
  try {
    await deleteWorkflow(currentWorkflowId.value)
    
    // 重新加载工作流列表
    await loadWorkflowList()
    
    // 如果还有其他工作流，加载第一个；否则清空
    if (workflowList.value.length > 0) {
      currentWorkflowId.value = workflowList.value[0].id
      await loadWorkflow()
    } else {
      currentWorkflowId.value = undefined
      resetWorkflow()
    }
    
    ElMessage.success('工作流已删除')
  } catch (error: any) {
    ElMessage.error('删除失败: ' + error.message)
  }
}

// 重置工作流（清空画布）
const resetWorkflow = () => {
  workflowName.value = ''
  workflowDescription.value = ''
  currentWorkflowId.value = undefined
  
  // 清空节点和边
  nodes.value = []
  edges.value = []
  
  // 清空历史
  history.value = []
  historyIndex.value = -1
}

// 加载工作流列表
const loadWorkflowList = async () => {
  try {
    workflowList.value = await listWorkflows()
  } catch (error: any) {
    ElMessage.error('加载工作流列表失败: ' + error.message)
  }
}

// 初始化
onMounted(async () => {
  // 加载工作流列表
  await loadWorkflowList()
  
  if (currentWorkflowId.value) {
    // 如果有 workflowId，加载它
    await loadWorkflow()
  } else if (workflowList.value.length > 0) {
    // 如果没有指定 ID 但有工作流，加载第一个
    currentWorkflowId.value = workflowList.value[0].id
    await loadWorkflow()
  } else {
    // 如果没有任何工作流，显示空画布
    resetWorkflow()
  }
  
  // 保存初始状态
  saveToHistory()
  
  // 添加键盘事件监听
  window.addEventListener('keydown', handleKeyDown)
})

onBeforeUnmount(() => {
  // 移除键盘事件监听
  window.removeEventListener('keydown', handleKeyDown)
  
  // 停止状态监控（SSE + 轮询）
  stopStatusMonitoring()
})
</script>

<style scoped lang="scss">
.workflow-editor {
  display: flex;
  flex-direction: column;
  height: 100%; /* Fit to parent container */
  background: var(--el-fill-color-lighter);
}

.editor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 20px;
  background: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color-light);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
  z-index: 10;

  .header-left {
    display: flex;
    align-items: center;
    gap: 12px;
    
    .workflow-selector {
      width: 280px;
      :deep(.el-input__wrapper) {
        font-size: 14px;
      }
    }
  }

  .header-actions {
    display: flex;
    gap: 8px;
  }
}

.editor-body {
  display: flex;
  flex: 1;
  overflow: hidden;
  min-height: 0; /* 确保 flex 子元素不会溢出 */
}

.left-panel {
  width: 260px;
  background: var(--el-bg-color);
  border-right: 1px solid var(--el-border-color-light);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  height: 100%;
}

.editor-canvas {
  flex: 1;
  position: relative;
  overflow: hidden;
  height: 100%;
}

.right-panel {
  width: 340px;
  background: var(--el-bg-color);
  border-left: 1px solid var(--el-border-color-light);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  height: 100%;
}

.editor-footer {
  height: 40px;
  background: var(--el-bg-color);
  border-top: 1px solid var(--el-border-color-light);
  display: flex;
  align-items: center;
  padding: 0 20px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
