<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount, markRaw } from 'vue'
import { VueFlow, useVueFlow, useGetPointerPosition, type NodeTypesObject } from '@vue-flow/core'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import { Background } from '@vue-flow/background'
import WorkflowNode from './WorkflowNode.vue'
import { Plus } from '@element-plus/icons-vue'
import { getWorkflowNodeTypes, type WorkflowNodeType } from '@renderer/api/workflows'

const nodeTypes: NodeTypesObject = {
  node: markRaw(WorkflowNode) as any,
}

const availableNodeTypes = ref<WorkflowNodeType[]>([])

type NodeConf = { id: string; type: string; params?: any; body?: NodeConf[] }

const props = defineProps<{ modelValue: any }>()
const emit = defineEmits<{ 'update:modelValue': [any]; 'select-node': [any]; 'request-insert': [any]; 'node-context': [any] }>()

const nodes = ref<any[]>([])
const edges = ref<any[]>([])
const selectedId = ref<string>('')
const isDragOver = ref(false)
const dslSource = ref<any>({ nodes: [] })
const { fitView, project } = useVueFlow()
const getPointerPosition = useGetPointerPosition()
const rootRef = ref<HTMLElement | null>(null)
let lastConnectSourceId: string | null = null
let lastHandleId: string | null = null

function buildFromDsl(dsl: any) {
  const _nodes: any[] = []
  const _edges: any[] = []
  
  // 检查是否是新的标准格式（包含edges数组）
  const isStandardFormat = Array.isArray(dsl?.edges)
  
  if (isStandardFormat) {
    // 标准 Vue Flow 格式
    const nodeList: any[] = Array.isArray(dsl?.nodes) ? dsl.nodes : []
    nodeList.forEach((n: any) => {
      const id = n.id || `n${Date.now()}`
      const isSel = !!(selectedId.value && n.id === selectedId.value)
      _nodes.push({
        id,
        type: 'node',
        data: { 
          type: n.type, 
          params: n.params || {}, 
          toolbarVisible: isSel,
          expanded: n.expanded || false
        },
        position: n.position || { x: 100, y: 100 }
      })
    })
    
    // 直接使用存储的edges
    const edgeList: any[] = Array.isArray(dsl?.edges) ? dsl.edges : []
    edgeList.forEach((e: any) => {
      _edges.push({
        id: e.id || `e-${e.source}-${e.target}`,
        source: e.source,
        target: e.target,
        sourceHandle: e.sourceHandle || 'r',
        targetHandle: e.targetHandle || 'l',
        animated: e.animated || false
      })
    })
  } else {
    // 兼容旧格式：从节点顺序推断布局
    const list: any[] = Array.isArray(dsl?.nodes) ? dsl.nodes : []
    const xGap = 420 // 进一步增加间距避免重叠 (260px + 160px margin)
    const yBase = 80
    
    // 主线节点：没有 layout.belowOf 的节点按顺序横向排列
    const main = list.filter((n: any) => !(n?.layout && n.layout.belowOf))
    main.forEach((n, i) => {
      const id = n.id || `n${i}`
      const isSel = !!(selectedId.value && (n.id ? n.id === selectedId.value : false))
      _nodes.push({ 
        id, 
        type: 'node',
        data: { type: n.type, params: n.params || {}, toolbarVisible: isSel, expanded: n.expanded || false }, 
        position: n.position || { x: 40 + i * xGap, y: yBase }
      })
      if (i > 0) _edges.push({ id: `e${i-1}-${i}`, source: main[i-1].id || `n${i-1}`, target: id, sourceHandle: 'r', targetHandle: 'l' })
      
      // ForEach body 节点
      if ((n.type === 'List.ForEach' || n.type === 'List.ForEachRange') && Array.isArray(n.body) && n.body.length) {
        n.body.forEach((bn: any, k: number) => {
          const bid = bn?.id || `${id}-b${k}`
          _nodes.push({ 
            id: bid, 
            type: 'node',
            data: { type: bn.type, params: bn.params || {}, expanded: bn.expanded || false }, 
            position: bn.position || { x: 40 + (i + k + 1) * xGap, y: yBase + 160 }
          })
          _edges.push({ id: `e-${id}-${bid}`, source: id, target: bid, sourceHandle: 'b', targetHandle: 't' })
        })
      }
    })
    
    // 垂直附着节点
    const attached = list.filter((n: any) => n?.layout && n.layout.belowOf)
    attached.forEach((n: any, j: number) => {
      const anchorId = n.layout.belowOf
      const anchorNode = _nodes.find(nn => nn.id === anchorId)
      const ax = anchorNode ? anchorNode.position.x : (40 + main.length * xGap)
      const id = n.id || `n_att_${j}`
      _nodes.push({ 
        id, 
        type: 'node',
        data: { type: n.type, params: n.params || {}, expanded: n.expanded || false }, 
        position: n.position || { x: ax, y: yBase + 160 }
      })
      _edges.push({ id: `e-${anchorId}-${id}`, source: anchorId, target: id, sourceHandle: 'b', targetHandle: 't' })
    })
  }
  
  return { nodes: _nodes, edges: _edges }
}

function rebuild() {
  const built = buildFromDsl(dslSource.value || { nodes: [] })
  nodes.value = built.nodes
  edges.value = built.edges
}

watch(() => props.modelValue, (v) => {
  dslSource.value = v || { nodes: [] }
  rebuild()
}, { immediate: true, deep: true })

watch(selectedId, () => { rebuild() })

onMounted(async () => {
  setTimeout(() => fitView({ padding: 0.2 }), 0)
  
  // 加载可用节点类型
  try {
    const result = await getWorkflowNodeTypes()
    availableNodeTypes.value = result.node_types
    console.log('✅ 已加载工作流节点类型:', availableNodeTypes.value)
  } catch (e) {
    console.error('加载节点类型失败:', e)
  }
  
  // 添加全局事件监听器
  if (typeof window !== 'undefined') {
    window.addEventListener('update-params', handleNodeParamsUpdate)
    window.addEventListener('update-expanded', handleNodeExpandedUpdate)
    window.addEventListener('delete-node', handleDeleteNode)
    window.addEventListener('wf-node-delete', handleDeleteNode) // 保持对原有事件的兼容
  }
})

// 组件卸载时清理事件监听器
onBeforeUnmount(() => {
  if (typeof window !== 'undefined') {
    window.removeEventListener('update-params', handleNodeParamsUpdate)
    window.removeEventListener('update-expanded', handleNodeExpandedUpdate)
    window.removeEventListener('delete-node', handleDeleteNode)
    window.removeEventListener('wf-node-delete', handleDeleteNode)
  }
})

function handlePaneContext(e: MouseEvent) {
  try {
    // 若右键发生在节点/边上，则交给子组件（用于弹出节点菜单）
    const tgt = e.target as HTMLElement | null
    if (tgt && (tgt.closest('.vue-flow__node') || tgt.closest('.vue-flow__edge'))) {
      return
    }
    e.preventDefault()
    // 画布右键菜单功能待实现
  } catch {}
}

function onConnectStart(params: any) {
  lastConnectSourceId = params?.nodeId || params?.node?.id || null
  lastHandleId = params?.handleId || params?.handle || null
}

function onConnectEnd() {
  lastConnectSourceId = null
  lastHandleId = null
  // 连接结束处理（如需要可在此添加逻辑）
}

function handleNodeClick(e: any) {
  try {
    selectedId.value = e?.node?.id || ''
    emit('select-node', e?.node)
  } catch {}
}

function handleEdgeClick(e: any) {
  try {
    const edgeId = e?.edge?.id
    if (!edgeId) return
    
    // 确认删除
    if (confirm('确定要删除这个连接吗？')) {
      // 从edges数组中移除该边
      edges.value = edges.value.filter(edge => edge.id !== edgeId)
      
      // 更新DSL
      const dsl = { ...dslSource.value }
      if (Array.isArray(dsl.edges)) {
        dsl.edges = dsl.edges.filter((edge: any) => edge.id !== edgeId)
      }
      dslSource.value = dsl
      emit('update:modelValue', dsl)
    }
  } catch (err) {
    console.warn('Edge click error:', err)
  }
}

function handleNodeContext(e: any) {
  try {
    selectedId.value = e?.node?.id || ''
    emit('node-context', e)
  } catch {}
}

// 监听节点位置变化
function handleNodeDragStop(e: any) {
  try {
    if (!e.node || !e.node.id) return
    updateNodePosition(e.node.id, e.node.position)
  } catch {}
}

// 监听连线变化
function handleConnect(params: any) {
  try {
    const newEdge = {
      id: `e-${params.source}-${params.target}`,
      source: params.source,
      target: params.target,
      sourceHandle: params.sourceHandle || 'r',
      targetHandle: params.targetHandle || 'l'
    }
    addEdge(newEdge)
  } catch {}
}

// 更新节点位置到DSL
function updateNodePosition(nodeId: string, position: { x: number; y: number }) {
  const currentDsl = dslSource.value || { nodes: [], edges: [] }
  
  // 确保DSL是标准格式
  if (!Array.isArray(currentDsl.edges)) {
    convertToStandardFormat()
    return
  }
  
  const nodeIndex = currentDsl.nodes.findIndex((n: any) => n.id === nodeId)
  if (nodeIndex >= 0) {
    currentDsl.nodes[nodeIndex] = {
      ...currentDsl.nodes[nodeIndex],
      position
    }
    emit('update:modelValue', { ...currentDsl })
  }
}

// 添加连线到DSL
function addEdge(edge: any) {
  const currentDsl = dslSource.value || { nodes: [], edges: [] }
  
  // 确保DSL是标准格式
  if (!Array.isArray(currentDsl.edges)) {
    convertToStandardFormat()
    return
  }
  
  // 检查是否已存在相同连线
  const exists = currentDsl.edges.some((e: any) => 
    e.source === edge.source && e.target === edge.target
  )
  
  if (!exists) {
    currentDsl.edges.push(edge)
    emit('update:modelValue', { ...currentDsl })
  }
}

// 将旧格式转换为标准格式
function convertToStandardFormat() {
  const currentDsl = dslSource.value || { nodes: [] }
  if (Array.isArray(currentDsl.edges)) return // 已经是标准格式
  
  const standardDsl = {
    ...currentDsl,
    edges: []
  }
  
  // 为现有节点添加位置信息
  if (Array.isArray(standardDsl.nodes)) {
    standardDsl.nodes.forEach((node: any, index: number) => {
      if (!node.position) {
        node.position = { x: 40 + index * 240, y: 80 }
      }
    })
  }
  
  emit('update:modelValue', standardDsl)
}

// 拖拽开始：设置拖拽数据
function onDragStart(event: DragEvent, nodeType: string) {
  if (event.dataTransfer) {
    event.dataTransfer.setData('application/vueflow', JSON.stringify({ type: nodeType }))
    event.dataTransfer.effectAllowed = 'move'
    
    // 设置拖拽反馈
    const target = event.target as HTMLElement
    if (target) {
      target.classList.add('dragging')
      // 创建拖拽预览
      const ghost = target.cloneNode(true) as HTMLElement
      ghost.style.transform = 'rotate(5deg)'
      ghost.style.opacity = '0.8'
      event.dataTransfer.setDragImage(ghost, ghost.offsetWidth / 2, ghost.offsetHeight / 2)
      
      // 清理样式
      setTimeout(() => {
        target.classList.remove('dragging')
      }, 100)
    }
  }
}

// 拖拽进入画布
function handleDragEnter(e: DragEvent) {
  e.preventDefault()
  isDragOver.value = true
}

// 拖拽离开画布
function handleDragLeave(e: DragEvent) {
  e.preventDefault()
  // 检查是否真的离开了画布区域
  const rect = rootRef.value?.getBoundingClientRect()
  if (rect) {
    const isOutside = e.clientX < rect.left || e.clientX > rect.right || 
                     e.clientY < rect.top || e.clientY > rect.bottom
    if (isOutside) {
      isDragOver.value = false
    }
  }
}

// 拖拽在画布上方
function handleDragOver(e: DragEvent) {
  e.preventDefault()
  isDragOver.value = true
}

// 处理节点参数更新
function handleNodeParamsUpdate(event: any) {
  const { nodeId, params } = event.detail || {}
  if (!nodeId || !params) return
  
  // 更新DSL中对应节点的参数
  const dsl = { ...dslSource.value }
  if (Array.isArray(dsl.nodes)) {
    const node = dsl.nodes.find((n: any) => n.id === nodeId)
    if (node) {
      node.params = { ...params }
      dslSource.value = dsl
      emit('update:modelValue', dsl)
    }
  }
}

// 处理节点展开状态更新
function handleNodeExpandedUpdate(event: any) {
  const { nodeId, expanded } = event.detail || {}
  if (!nodeId) return
  
  // 更新DSL中对应节点的展开状态
  const dsl = { ...dslSource.value }
  if (Array.isArray(dsl.nodes)) {
    const node = dsl.nodes.find((n: any) => n.id === nodeId)
    if (node) {
      node.expanded = expanded
      dslSource.value = dsl
      emit('update:modelValue', dsl)
    }
  }
}

// 处理节点删除
function handleDeleteNode(event: any) {
  const { nodeId } = event.detail || {}
  if (!nodeId) return
  
  // 从DSL中删除对应节点
  const dsl = { ...dslSource.value }
  if (Array.isArray(dsl.nodes)) {
    dsl.nodes = dsl.nodes.filter((n: any) => n.id !== nodeId)
    
    // 删除相关边
    if (Array.isArray(dsl.edges)) {
      dsl.edges = dsl.edges.filter((e: any) => e.source !== nodeId && e.target !== nodeId)
    }
    
    dslSource.value = dsl
    emit('update:modelValue', dsl)
  }
}

// 拖拽上图：从"节点库"拖拽的 dataTransfer.text 期望携带 { type: 'Card.Read' | ... }
function handleDrop(e: DragEvent) {
  e.preventDefault()
  isDragOver.value = false
  
  try {
    const data = e.dataTransfer?.getData('application/vueflow') || 
                 e.dataTransfer?.getData('application/json') || 
                 e.dataTransfer?.getData('text/plain') || ''
    if (!data) return
    const parsed = JSON.parse(data)
    if (!parsed || !parsed.type) return
    
    // 使用 Vue Flow 官方 API 获取指针位置（正确处理缩放/平移）
    const position = getPointerPosition(e)
    
    emit('request-insert', { 
      newNodeType: parsed.type,
      position: {
        x: Math.max(0, position.x - 130), // 节点宽度的一半 (260px / 2)，让鼠标在节点中心
        y: Math.max(0, position.y - 50)   // 节点高度的一半
      }
    })
  } catch (err) {
    console.warn('Drop handling failed:', err)
  }
}
</script>

<template>
  <div class="wf-canvas-container">
    <div 
      class="wf-canvas" 
      :class="{ 'drag-over': isDragOver }"
      ref="rootRef" 
      @contextmenu.stop.prevent="handlePaneContext" 
      @dragenter="handleDragEnter"
      @dragleave="handleDragLeave"
      @dragover="handleDragOver"
      @drop="handleDrop"
    >
      <VueFlow 
        :nodes="nodes" 
        :edges="edges" 
        :node-types="nodeTypes" 
        @node-click="handleNodeClick" 
        @nodeClick="handleNodeClick" 
        @connectStart="onConnectStart" 
        @connectEnd="onConnectEnd" 
        @node-contextmenu="handleNodeContext"
        @node-drag-stop="handleNodeDragStop"
        @connect="handleConnect"
        @edge-click="handleEdgeClick"
        @update-params="handleNodeParamsUpdate"
        @update-expanded="handleNodeExpandedUpdate"
        @delete-node="handleDeleteNode"
      >
        <Background />
      </VueFlow>
      
      <!-- 拖拽提示层 -->
      <div v-if="isDragOver" class="drag-overlay">
        <div class="drag-hint">
          <el-icon size="24"><Plus /></el-icon>
          <span>松开鼠标创建节点</span>
        </div>
      </div>
    </div>
    
    <!-- 底部节点库栏 -->
    <div class="node-library">
      <div class="library-title">你可以拖拽这些节点到画布上</div>
      <div class="library-nodes">
        <div 
          v-for="nodeType in availableNodeTypes"
          :key="nodeType.type"
          class="library-node" 
          draggable="true" 
          @dragstart="onDragStart($event, nodeType.type)"
        >
          <div class="node-title">{{ nodeType.name }}</div>
          <div class="node-desc">{{ nodeType.description }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.wf-canvas-container { display: flex; flex-direction: column; height: 70vh; }
.wf-canvas { flex: 1; border: 1px solid var(--el-border-color); border-radius: 6px 6px 0 0; overflow: hidden; }

.node-library { 
  background: #4ade80; 
  color: white; 
  padding: 12px; 
  border-radius: 0 0 6px 6px;
  border: 1px solid var(--el-border-color);
  border-top: none;
}

.library-title { 
  font-size: 14px; 
  font-weight: 600; 
  margin-bottom: 8px; 
  text-align: center;
}

.library-nodes { 
  display: flex; 
  gap: 12px; 
  justify-content: center; 
  flex-wrap: wrap;
}

.library-node { 
  background: rgba(255, 255, 255, 0.2); 
  border: 1px solid rgba(255, 255, 255, 0.3);
  border-radius: 8px; 
  padding: 8px 12px; 
  cursor: grab; 
  transition: all 0.2s;
  min-width: 100px;
  text-align: center;
}

.library-node:hover { 
  background: rgba(255, 255, 255, 0.3); 
  transform: translateY(-2px);
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
}

.library-node.dragging {
  opacity: 0.5;
  transform: rotate(5deg) scale(0.95);
}

/* 拖拽反馈样式 */
.wf-canvas.drag-over {
  background: linear-gradient(45deg, rgba(64, 158, 255, 0.05) 25%, transparent 25%),
              linear-gradient(-45deg, rgba(64, 158, 255, 0.05) 25%, transparent 25%),
              linear-gradient(45deg, transparent 75%, rgba(64, 158, 255, 0.05) 75%),
              linear-gradient(-45deg, transparent 75%, rgba(64, 158, 255, 0.05) 75%);
  background-size: 20px 20px;
  background-position: 0 0, 0 10px, 10px -10px, -10px 0px;
}

.drag-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(64, 158, 255, 0.1);
  border: 2px dashed #409eff;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
  z-index: 1000;
}

.drag-hint {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: #409eff;
  font-size: 16px;
  font-weight: 500;
}

.drag-hint .el-icon {
  animation: bounce 1s infinite;
}

@keyframes bounce {
  0%, 20%, 50%, 80%, 100% {
    transform: translateY(0);
  }
  40% {
    transform: translateY(-10px);
  }
  60% {
    transform: translateY(-5px);
  }
}

.library-node:active { 
  cursor: grabbing; 
  transform: translateY(0);
}

.node-title { 
  font-weight: 600; 
  font-size: 12px; 
  margin-bottom: 2px;
}

.node-desc { 
  font-size: 11px; 
  opacity: 0.9;
}
</style>


