<script setup lang="ts">
import { ref, watch, onMounted, markRaw } from 'vue'
import { VueFlow, useVueFlow, type NodeTypesObject } from '@vue-flow/core'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import { Background } from '@vue-flow/background'
import WorkflowNode from './WorkflowNode.vue'
const nodeTypes: NodeTypesObject = { wf: markRaw(WorkflowNode) as any }

type NodeConf = { id: string; type: string; params?: any; body?: NodeConf[] }

const props = defineProps<{ modelValue: any }>()
const emit = defineEmits<{ 'update:modelValue': [any]; 'select-node': [any]; 'request-insert': [any]; 'node-context': [any] }>()

const nodes = ref<any[]>([])
const edges = ref<any[]>([])
const selectedId = ref<string>('')
const dslSource = ref<any>({ nodes: [] })
const { fitView } = useVueFlow()
const rootRef = ref<HTMLElement | null>(null)
let lastConnectSourceId: string | null = null
let lastHandleId: string | null = null

function buildFromDsl(dsl: any) {
  const _nodes: any[] = []
  const _edges: any[] = []
  const list: any[] = Array.isArray(dsl?.nodes) ? dsl.nodes : []
  const xGap = 240
  const yBase = 80
  // 主线节点：没有 layout.belowOf 的节点按顺序横向排列
  const main = list.filter((n: any) => !(n?.layout && n.layout.belowOf))
  main.forEach((n, i) => {
    const id = n.id || `n${i}`
    const isSel = !!(selectedId.value && (n.id ? n.id === selectedId.value : false))
    _nodes.push({ id, type: 'wf', data: { type: n.type, params: n.params || {}, toolbarVisible: isSel }, position: { x: 40 + i * xGap, y: yBase } })
    if (i > 0) _edges.push({ id: `e${i-1}-${i}`, source: main[i-1].id || `n${i-1}`, target: id, sourceHandle: 'r', targetHandle: 'l' })
    if ((n.type === 'List.ForEach' || n.type === 'List.ForEachRange') && Array.isArray(n.body) && n.body.length) {
      n.body.forEach((bn: any, k: number) => {
        const bid = bn?.id || `${id}-b${k}`
        _nodes.push({ id: bid, type: 'wf', data: { type: bn.type, params: bn.params || {} }, position: { x: 40 + (i + k + 1) * xGap, y: yBase + 160 } })
        _edges.push({ id: `e-${id}-${bid}` , source: id, target: bid, sourceHandle: 'b', targetHandle: 't' })
      })
    }
  })
  // 垂直附着：layout.belowOf 存在时，放到对应锚点下方
  const attached = list.filter((n: any) => n?.layout && n.layout.belowOf)
  attached.forEach((n: any, j: number) => {
    const anchorId = n.layout.belowOf
    const anchorNode = _nodes.find(nn => nn.id === anchorId)
    const ax = anchorNode ? anchorNode.position.x : (40 + main.length * xGap)
    const id = n.id || `n_att_${j}`
    _nodes.push({ id, type: 'wf', data: { type: n.type, params: n.params || {} }, position: { x: ax, y: yBase + 160 } })
    _edges.push({ id: `e-${anchorId}-${id}`, source: anchorId, target: id, sourceHandle: 'b', targetHandle: 't' })
  })
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

onMounted(() => setTimeout(() => fitView({ padding: 0.2 }), 0))

function handlePaneContext(e: MouseEvent) {
  try {
    // 若右键发生在节点/边上，则交给子组件（用于弹出节点菜单）
    const tgt = e.target as HTMLElement | null
    if (tgt && (tgt.closest('.vue-flow__node') || tgt.closest('.vue-flow__edge'))) {
      return
    }
    e.preventDefault()
    const rect = rootRef.value?.getBoundingClientRect()
    const relX = rect ? (e.clientX - rect.left) : 0
    const xGap = 240
    const index = nodes.value.filter(n => (n?.position?.x ?? 0) + xGap / 2 < relX).length
    emit('request-insert', { index })
  } catch {}
}

function onConnectStart(params: any) {
  lastConnectSourceId = params?.nodeId || params?.node?.id || null
  lastHandleId = params?.handleId || params?.handle || null
}

function onConnectEnd() {
  if (!lastConnectSourceId) return
  const idx = nodes.value.findIndex(n => n.id === lastConnectSourceId)
  lastConnectSourceId = null
  const placement = lastHandleId === 'b' ? 'below' : 'right'
  lastHandleId = null
  if (idx >= 0) emit('request-insert', { index: idx + 1, anchorId: nodes.value[idx].id, placement })
}

function handleNodeClick(e: any) {
  try {
    selectedId.value = e?.node?.id || ''
    emit('select-node', e?.node)
  } catch {}
}

function handleNodeContext(e: any) {
  try {
    selectedId.value = e?.node?.id || ''
    emit('node-context', e)
  } catch {}
}
</script>

<template>
  <div class="wf-canvas" ref="rootRef" @contextmenu.stop.prevent="handlePaneContext">
    <VueFlow :nodes="nodes" :edges="edges" :node-types="nodeTypes" @node-click="handleNodeClick" @nodeClick="handleNodeClick" @connectStart="onConnectStart" @connectEnd="onConnectEnd" @node-contextmenu="handleNodeContext">
      <Background />
    </VueFlow>
  </div>
</template>

<style scoped>
.wf-canvas { height: 60vh; border: 1px solid var(--el-border-color); border-radius: 6px; overflow: hidden; }
</style>


