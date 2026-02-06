<template>
  <div class="workflow-canvas">
    <VueFlow
      v-model:nodes="nodes"
      v-model:edges="edges"
      :node-types="nodeTypes"
      :default-zoom="1"
      :min-zoom="0.2"
      :max-zoom="2"
      :fit-view-on-init="false"
      @node-click="handleNodeClick"
      @edge-click="handleEdgeClick"
      @pane-click="handlePaneClick"
      @drop="handleDrop"
      @dragover="handleDragOver"
    >
      <!-- 背景网格 -->
      <Background 
        :pattern-color="isDarkMode ? '#555' : '#aaa'" 
        :gap="20" 
        :size="1"
      />
    </VueFlow>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, markRaw, computed, provide } from 'vue'
import { VueFlow, useVueFlow, MarkerType } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import BaseNode from '@/components/workflow-v2/nodes/BaseNode.vue'
import ConditionNode from '@/components/workflow-v2/nodes/ConditionNode.vue'
import DisplayNode from '@/components/workflow-v2/nodes/DisplayNode.vue'
import { useWorkflowStore } from '@/stores/useWorkflowStore'
import { useAppStore } from '@/stores/useAppStore'

const workflowStore = useWorkflowStore()
const appStore = useAppStore()

// 暗黑模式状态
const isDarkMode = computed(() => appStore.isDarkMode)

// 组件映射表
const componentMap: Record<string, any> = {
  'BaseNode': BaseNode,
  'ConditionNode': ConditionNode,
  'DisplayNode': DisplayNode,
  // 特殊映射
  'Logic.Condition': ConditionNode,
  'Logic.Display': DisplayNode
}

// 动态计算节点类型映射
const nodeTypes = computed(() => {
  const types: Record<string, any> = {}
  
  // 1. 注册所有服务端返回的节点类型
  workflowStore.nodeTypes.forEach(node => {
    // 默认使用 BaseNode，除非有特殊映射
    types[node.type] = markRaw(componentMap[node.type] || BaseNode)
  })
  
  // 2. 确保特殊节点总是被注册 (即使服务端暂未返回)
  types['Logic.Condition'] = markRaw(ConditionNode)
  types['Logic.Display'] = markRaw(DisplayNode)
  
  return types
})

const props = defineProps<{
  nodes: any[]
  edges: any[]
  selectedNodeId: string | null
}>()

const emit = defineEmits<{
  'update:nodes': [nodes: any[]]
  'update:edges': [edges: any[]]
  'node-click': [nodeId: string]
  'edge-click': [edgeId: string]
  'pane-click': []
  'add-node': [payload: { nodeId: string; handleId?: string; event: MouseEvent }]
}>()

// 提供给子组件的方法
provide('onAddNode', (payload: { nodeId: string; handleId?: string; event: MouseEvent }) => {
  emit('add-node', payload)
})

const { 
  onConnect, 
  project,
  onNodeDoubleClick,
  onNodeDragStop,  // 拖拽停止事件
  onNodesChange    // 节点变化事件
} = useVueFlow()

// 监听节点双击事件（临时方案，后续改为单击端口）
onNodeDoubleClick(({ node }) => {
  const event = new MouseEvent('click', {
    clientX: node.position.x + 300,
    clientY: node.position.y + 100
  })
  emit('add-node', { nodeId: node.id, event: event as any })
})

// 同步nodes和edges（只从props到本地）
const nodes = ref(props.nodes)
const edges = ref(props.edges)

// 只监听props变化，单向从父组件更新到本地状态
watch(() => props.nodes, (newNodes) => {
  nodes.value = newNodes
})

watch(() => props.edges, (newEdges) => {
  edges.value = newEdges
})

// 节点拖拽停止时发出更新（避免拖拽过程中频繁触发）
onNodeDragStop(() => {
  emit('update:nodes', nodes.value)
})

// 节点变化时发出更新（非拖拽的变化，如添加、删除）
onNodesChange((changes) => {
  // 只在非拖拽变化时发出更新（拖拽由onNodeDragStop处理）
  const hasDragChange = changes.some(c => c.type === 'position' && c.dragging)
  if (!hasDragChange) {
    emit('update:nodes', nodes.value)
  }
})

// 边变化时立即发出（边的变化不频繁）
watch(edges, (newEdges) => {
  emit('update:edges', newEdges)
})

// 连接节点
onConnect((params) => {
  // 0. 检查目标端口是否已有连接，如果有则删除旧连接（单输入端口限制）
  if (params.target && params.targetHandle) {
    const existingEdges = edges.value.filter(
      e => e.target === params.target && e.targetHandle === params.targetHandle
    )
    if (existingEdges.length > 0) {
      // 删除所有连接到该目标端口的旧边
      edges.value = edges.value.filter(
        e => !(e.target === params.target && e.targetHandle === params.targetHandle)
      )
      console.log(`[WorkflowCanvas] 自动断开旧连接: ${existingEdges.length} 条`)
    }
  }
  
  // 1. 处理依赖连接 (dep-output -> dep-input)
  if (params.sourceHandle === 'dep-output' && params.targetHandle === 'dep-input') {
    const newEdge: any = {
      ...params,
      id: `dep-${params.source}-${params.target}`,
      animated: true,
      style: { strokeDasharray: '5,5', stroke: '#909399', opacity: 0.8 }, // 灰色虚线
      type: 'default',
      data: { isDependency: true } // 标记为依赖边
    }
    edges.value.push(newEdge)
    return
  }

  // 2. 防止混合连接 (数据端口 <-> 依赖端口)
  if (
    params.sourceHandle?.startsWith('dep-') || 
    params.targetHandle?.startsWith('dep-')
  ) {
    // 阻止无效连接
    return
  }

  // 3. 处理数据连接
  // 根据sourceHandle判断连接类型
  let edgeStyle = { strokeWidth: 2, stroke: '#409eff' }
  let edgeLabel = ''
  let labelBgColor = '#409eff'
  
  if (params.sourceHandle === 'true') {
    edgeStyle = { strokeWidth: 2, stroke: '#67c23a' }  // 绿色
    edgeLabel = 'True'
    labelBgColor = '#67c23a'
  } else if (params.sourceHandle === 'false') {
    edgeStyle = { strokeWidth: 2, stroke: '#f56c6c' }  // 红色
    edgeLabel = 'False'
    labelBgColor = '#f56c6c'
  }
  
  const newEdge: any = {
    ...params,
    id: `edge-${Date.now()}`,
    animated: true,
    style: edgeStyle,
    markerEnd: MarkerType.ArrowClosed,
    data: { isDependency: false }
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
})

// 节点点击
const handleNodeClick = (event: any) => {
  emit('node-click', event.node.id)
}

// 边点击
const handleEdgeClick = (event: any) => {
  emit('edge-click', event.edge.id)
}

// 删除选中的边（按Delete键）
const handleKeyDown = (event: KeyboardEvent) => {
  if (event.key === 'Delete' || event.key === 'Backspace') {
    // 如果有选中的边，删除它
    const selectedEdge = edges.value.find(e => e.selected)
    if (selectedEdge) {
      edges.value = edges.value.filter(e => e.id !== selectedEdge.id)
      event.preventDefault()
    }
  }
}

// 监听键盘事件
if (typeof window !== 'undefined') {
  window.addEventListener('keydown', handleKeyDown)
}

// 画布点击
const handlePaneClick = () => {
  emit('pane-click')
}

// 节点端口点击（触发快捷菜单）
const handleAddNodeClick = (nodeId: string, handleId: string | undefined, event: MouseEvent) => {
  emit('add-node', { nodeId, handleId, event })
}

// 拖拽放置
const handleDrop = (event: DragEvent) => {
  event.preventDefault()
  
  const data = event.dataTransfer?.getData('application/vueflow')
  if (!data) return
  
  const nodeData = JSON.parse(data)
  const position = project({ 
    x: event.clientX - 100, 
    y: event.clientY - 50 
  })
  
  const newNode = {
    id: `node-${Date.now()}`,
    type: nodeData.type,
    position,
    data: {
      label: nodeData.label,
      description: nodeData.description,
      config: {}
    }
  }
  
  nodes.value.push(newNode)
}

const handleDragOver = (event: DragEvent) => {
  event.preventDefault()
  if (event.dataTransfer) {
    event.dataTransfer.dropEffect = 'copy'
  }
}

</script>

<style scoped lang="scss">
.workflow-canvas {
  width: 100%;
  height: 100%;
  position: relative;
  background: var(--el-fill-color-lighter);
}

:deep(.vue-flow__node) {
  cursor: pointer;
}

:deep(.vue-flow__edge) {
  cursor: pointer;
  
  &.selected {
    .vue-flow__edge-path {
      stroke-width: 3 !important;
    }
  }
  
  &:hover {
    .vue-flow__edge-path {
      stroke-width: 3 !important;
    }
  }
}

:deep(.vue-flow__edge-text) {
  font-size: 11px;
  font-weight: 600;
  fill: #606266;
  background: #fff;
  padding: 2px 6px;
  border-radius: 3px;
}

:deep(.vue-flow) {
  width: 100%;
  height: 100%;
}

// 箭头颜色
:deep(.vue-flow__edge) {
  .vue-flow__edge-path {
    stroke-width: 2;
  }
  
  // 绿色箭头（True）
  &[data-source-handle="true"] {
    .vue-flow__arrowhead {
      fill: #67c23a;
    }
  }
  
  // 红色箭头（False）
  &[data-source-handle="false"] {
    .vue-flow__arrowhead {
      fill: #f56c6c;
    }
  }
  
  // 默认蓝色箭头
  .vue-flow__arrowhead {
    fill: #409eff;
  }
}
</style>
