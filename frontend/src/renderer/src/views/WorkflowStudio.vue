<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import WorkflowCanvas from '@renderer/components/workflow/WorkflowCanvas.vue'
import WorkflowParamPanel from '@renderer/components/workflow/WorkflowParamPanel.vue'
import { useVueFlow } from '@vue-flow/core'
import { listWorkflows, getWorkflow, updateWorkflow, validateWorkflow, listWorkflowTriggers, createWorkflowTrigger, updateWorkflowTrigger, deleteWorkflowTrigger, type WorkflowTriggerRead, createWorkflow, deleteWorkflow } from '@renderer/api/workflows'
import { ElMessageBox, ElMessage } from 'element-plus'
import { Edit, Delete as DeleteIcon } from '@element-plus/icons-vue'
import { getCardTypes, type CardTypeRead } from '@renderer/api/cards'

onMounted(() => { document.title = 'Workflow Studio - Novel Forge' })
// 节点工具栏：统一响应删除
if (typeof window !== 'undefined') {
  window.addEventListener('wf-node-delete', (e: any) => {
    const id = e?.detail?.id
    if (!id) return
    try {
      const list: any[] = Array.isArray(dsl.value.nodes) ? dsl.value.nodes : []
      const idx = list.findIndex((n: any, i: number) => (n.id || `n${i}`) === id)
      if (idx < 0) return
      const next = list.slice(); next.splice(idx,1)
      dsl.value = { ...(dsl.value || {}), nodes: next }
    } catch {}
  })
}

const workflows = ref<any[]>([])
const selectedId = ref<number | null>(null)
const dsl = ref<any>({ nodes: [] })
const errors = ref<string[]>([])
const selectedNode = ref<any | null>(null)
const cardTypes = ref<CardTypeRead[]>([])
const previewTypeName = ref<string>('')
const triggers = ref<WorkflowTriggerRead[]>([])
const triggerDialogVisible = ref(false)
const editingTrigger = ref<Partial<WorkflowTriggerRead & { is_new?: boolean }>>({})
const paramWidth = ref<number>(320)
let resizing = false
let startX = 0
let startW = 320
const nodeLibVisible = ref(false)
const ctxMenu = ref<{ visible: boolean; x: number; y: number }>({ visible: false, x: 0, y: 0 })
function onNodeContext(e: any) {
  try {
    selectedNode.value = e?.node || selectedNode.value
    const ev: MouseEvent | undefined = e?.event
    ctxMenu.value = { visible: true, x: Number(ev?.clientX || 0), y: Number(ev?.clientY || 0) }
    ;(e?.event || e)?.preventDefault?.()
  } catch {}
}

async function loadList() {
  workflows.value = await listWorkflows()
  if (!selectedId.value && workflows.value.length) select(workflows.value[0].id)
}

async function select(id: number) {
  selectedId.value = id
  const wf = await getWorkflow(id)
  dsl.value = wf.definition_json || { name: wf.name, dsl_version: 1, nodes: [] }
  errors.value = []
  try {
    triggers.value = (await listWorkflowTriggers()).filter(t => t.workflow_id === id)
  } catch {}

  // 若首节点为 Card.Read 且未设置 type_name，则用预览类型（或默认“世界观设定”）补齐，便于后续字段解析
  try {
    const nodes: any[] = Array.isArray(dsl.value.nodes) ? dsl.value.nodes : []
    const firstRead = nodes.find(n => n?.type === 'Card.Read')
    const typeFromDsl = firstRead?.params?.type_name
    const typeFromTrigger = (triggers.value.find(t => !!t.card_type_name)?.card_type_name) as string | undefined
    const smart = (wf.name || '').includes('世界观') ? '世界观设定' : undefined
    const decided = typeFromDsl || typeFromTrigger || smart || ''
    if (firstRead) {
      firstRead.params = { ...(firstRead.params || {}), type_name: (firstRead.params?.type_name || decided) }
    }
    if (decided) previewTypeName.value = decided
  } catch {}
}

function setFirstReadTypeName(typeName: string) {
  try {
    const nodes: any[] = Array.isArray(dsl.value.nodes) ? dsl.value.nodes : []
    const firstRead = nodes.find(n => n?.type === 'Card.Read')
    if (firstRead) firstRead.params = { ...(firstRead.params || {}), type_name: typeName }
  } catch {}
}

watch(previewTypeName, (v) => {
  if (v) setFirstReadTypeName(v)
})

async function save() {
  const wid = Number(selectedId.value)
  if (!Number.isFinite(wid)) return
  try {
    await updateWorkflow(wid, { definition_json: dsl.value })
    // 重新读取以确认后端已持久化
    const wf = await getWorkflow(wid)
    dsl.value = wf.definition_json || dsl.value
    ElMessage.success('已保存')
  } catch (e:any) {
    ElMessage.error('保存失败')
    console.error(e)
  }
}

const createDialogVisible = ref(false)
const newWorkflowName = ref('')
async function createNew() {
  newWorkflowName.value = ''
  createDialogVisible.value = true
}
async function confirmCreate() {
  const name = (newWorkflowName.value || '').trim()
  if (!name) { createDialogVisible.value = false; return }
  const wf = await createWorkflow({ name, definition_json: { dsl_version: 1, name, nodes: [] }, is_active: true })
  await loadList()
  if (wf?.id) await select(wf.id)
  createDialogVisible.value = false
}

async function removeSelected() {
  const wid = Number(selectedId.value)
  if (!Number.isFinite(wid)) return
  try {
    await ElMessageBox.confirm('确认删除该工作流？此操作不可恢复', '删除确认', { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' })
  } catch { return }
  await deleteWorkflow(wid)
  selectedId.value = null
  dsl.value = { nodes: [] }
  await loadList()
  ElMessage.success('已删除')
}

async function validateNow() {
  const wid = Number(selectedId.value)
  if (!Number.isFinite(wid)) return
  const v = await validateWorkflow(wid)
  errors.value = v.errors || []
}

loadList()
getCardTypes().then(v => { cardTypes.value = v }).catch(() => {})

function onNodeSelected(node: any) {
  selectedNode.value = node || null
}

function updateParams(next: any) {
  // 将右侧面板的参数写回 DSL（支持顶层与 body 递归）
  if (!selectedNode.value) return
  const id = String(selectedNode.value.id || '')
  // no-op debug log removed

  function applyPatch(list: any[]): boolean {
    for (let i = 0; i < list.length; i++) {
      const n = list[i]
      const nid = String(n?.id || `n${i}`)
      if (nid === id) {
        const before = JSON.parse(JSON.stringify(n.params || {}))
        n.params = { ...(n.params || {}), ...next }
        // no-op debug log removed
        if (selectedNode.value?.data) selectedNode.value.data.params = n.params
        return true
      }
      if (Array.isArray(n?.body)) {
        // 子节点用自身 id 做匹配，不再用绘制时拼出来的 id
        for (let k = 0; k < n.body.length; k++) {
          const bn = n.body[k]
          const bid = String(bn?.id || `${n.id || `n${i}`}-b${k}`)
          if (bid === id) {
            const beforeB = JSON.parse(JSON.stringify(bn.params || {}))
            bn.params = { ...(bn.params || {}), ...next }
            // no-op debug log removed
            if (selectedNode.value?.data) selectedNode.value.data.params = bn.params
            return true
          }
          if (Array.isArray(bn?.body) && applyPatch([bn])) return true
        }
      }
    }
    return false
  }

  const root = Array.isArray(dsl.value?.nodes) ? dsl.value.nodes : []
  if (!applyPatch(root)) return
  dsl.value = { ...(dsl.value || {}), nodes: JSON.parse(JSON.stringify(root)) }
}

function startResize(e: MouseEvent) {
  resizing = true
  startX = e.clientX
  startW = paramWidth.value
  const onMove = (ev: MouseEvent) => {
    if (!resizing) return
    const dx = ev.clientX - startX
    // 面板位于右侧，拖拽左侧边缘：向左拖应增宽，向右拖应变窄
    let w = startW - dx
    if (w < 260) w = 260
    if (w > 560) w = 560
    paramWidth.value = w
  }
  const onUp = () => {
    resizing = false
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
  }
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}

function insertNode(spec: any) {
  try {
    const nodes: any[] = Array.isArray(dsl.value.nodes) ? dsl.value.nodes : []
    const idx = (pendingInsertIndex.value != null) ? pendingInsertIndex.value : (selectedNode.value ? (nodes.findIndex((n: any, i: number) => (n.id || `n${i}`) === selectedNode.value.id) + 1) : nodes.length)
    const newNode: any = { id: `n${Date.now()}`, type: spec.type, params: spec.params || {} }
    if (pendingBelowOf) newNode.layout = { belowOf: pendingBelowOf }
    if (spec.body && Array.isArray(spec.body)) newNode['body'] = spec.body
    const next = nodes.slice(0, Math.max(0, idx))
    next.push(newNode)
    for (let i = Math.max(0, idx); i < nodes.length; i++) next.push(nodes[i])
    dsl.value = { ...(dsl.value || {}), nodes: next }
    nodeLibVisible.value = false
    pendingInsertIndex.value = null
    pendingBelowOf = null
  } catch {}
}

const pendingInsertIndex = ref<number | null>(null)
let pendingBelowOf: string | null = null
function openNodeLibAt(payload: any) {
  const index = Math.max(0, Math.min(Number(payload?.index ?? (dsl.value?.nodes || []).length), (dsl.value?.nodes || []).length))
  pendingInsertIndex.value = index
  pendingBelowOf = payload?.placement === 'below' ? String(payload?.anchorId || '') : null
  nodeLibVisible.value = true
}

function openCreateTrigger() {
  if (!selectedId.value) return
  editingTrigger.value = { workflow_id: Number(selectedId.value), trigger_on: 'onsave', card_type_name: '', is_active: true, is_new: true }
  triggerDialogVisible.value = true
}

async function saveTrigger() {
  const t = editingTrigger.value
  if (!t) return
  if ((t as any).is_new) {
    const created = await createWorkflowTrigger({ workflow_id: Number(selectedId.value), trigger_on: String(t.trigger_on || 'onsave'), card_type_name: (t.card_type_name || undefined), is_active: t.is_active !== false })
    triggers.value = [...triggers.value, created]
  } else if (t.id) {
    const updated = await updateWorkflowTrigger(Number(t.id), { trigger_on: t.trigger_on, card_type_name: t.card_type_name, is_active: t.is_active })
    const i = triggers.value.findIndex(x => x.id === updated.id)
    if (i >= 0) triggers.value[i] = updated
  }
  triggerDialogVisible.value = false
}

async function removeTrigger(id: number) {
  await deleteWorkflowTrigger(id)
  triggers.value = triggers.value.filter(t => t.id !== id)
}

function deleteSelectedNode() {
  try {
    if (!selectedNode.value) return
    const id = selectedNode.value.id as string
    const list: any[] = Array.isArray(dsl.value.nodes) ? dsl.value.nodes : []
    const idx = list.findIndex((n: any, i: number) => (n.id || `n${i}`) === id)
    if (idx < 0) return
    const next = list.slice()
    next.splice(idx, 1)
    dsl.value = { ...(dsl.value || {}), nodes: next }
    selectedNode.value = null
    ctxMenu.value.visible = false
  } catch {}
}
</script>

<template>
  <div class="workflow-studio">
    <div class="header">
      <h2>工作流工作室</h2>
    </div>
    <div class="layout">
      <div class="left">
        <el-scrollbar class="list">
          <el-menu :default-active="String(selectedId || '')" @select="(k: string) => select(Number(k))">
            <el-menu-item v-for="w in workflows" :index="String(w.id)" :key="w.id">
              <div class="item" :class="{ active: selectedId === w.id }">
                <div class="name">{{ w.name }}</div>
                <div class="meta">v{{ w.version }}<span v-if="w.is_built_in" class="tag">内置</span><span class="dsl">dsl{{ w.dsl_version }}</span></div>
              </div>
            </el-menu-item>
          </el-menu>
        </el-scrollbar>
      </div>
      <div class="right">
        <div class="toolbar">
          <el-button type="primary" @click="save">保存</el-button>
          <el-button @click="createNew">新建</el-button>
          <el-button type="danger" @click="removeSelected" :disabled="!selectedId">删除</el-button>
          <el-button @click="validateNow">校验</el-button>
          <el-tag v-if="errors.length" type="danger">有 {{ errors.length }} 个错误</el-tag>
          <div style="flex:1"></div>
          <span class="label">预览卡片类型</span>
          <el-select v-model="previewTypeName" size="small" style="width:220px">
            <el-option v-for="t in cardTypes" :key="t.id" :label="t.name" :value="t.name" />
          </el-select>
          <span class="label" style="margin-left:12px">触发器</span>
          <el-tag v-for="tg in triggers" :key="tg.id" effect="plain" style="margin-left:4px" type="info">
            {{ tg.trigger_on }}{{ tg.card_type_name ? `:${tg.card_type_name}` : '' }}
            <el-icon style="margin-left:4px; cursor:pointer" @click="editingTrigger={...tg};triggerDialogVisible=true"><Edit/></el-icon>
            <el-icon style="margin-left:4px; cursor:pointer" @click="removeTrigger(tg.id)"><DeleteIcon/></el-icon>
          </el-tag>
          <el-button size="small" @click="openCreateTrigger">新增触发器</el-button>
          <el-button size="small" @click="nodeLibVisible=true">节点库</el-button>
        </div>
        <div class="canvas-and-panel">
          <WorkflowCanvas v-model="dsl" @select-node="onNodeSelected" @request-insert="(p:any)=>openNodeLibAt(p)" @node-context="onNodeContext" />
          <div class="param-wrap" :style="{ width: paramWidth + 'px' }">
            <WorkflowParamPanel class="param-panel" :key="selectedNode?.id || 'none'" :node="selectedNode" :context-type-name="previewTypeName" @update-params="updateParams" />
            <div class="resizer" @mousedown="startResize"></div>
          </div>
        </div>
        <div class="json"><pre>{{ dsl }}</pre></div>

        <div v-if="ctxMenu.visible" class="ctx" :style="{ left: ctxMenu.x + 'px', top: ctxMenu.y + 'px' }" @click.stop @contextmenu.stop.prevent>
          <el-card shadow="hover" class="ctx-card">
            <div class="ctx-item" @click="deleteSelectedNode"><el-icon><DeleteIcon/></el-icon><span>删除节点</span></div>
          </el-card>
        </div>

        <el-dialog v-model="triggerDialogVisible" title="触发器" width="420px">
          <el-form label-width="100px" size="small">
            <el-form-item label="触发时机">
              <el-select v-model="(editingTrigger as any).trigger_on">
                <el-option label="onsave" value="onsave" />
                <el-option label="ongenfinish" value="ongenfinish" />
                <el-option label="manual" value="manual" />
              </el-select>
            </el-form-item>
            <el-form-item label="卡片类型(可选)">
              <el-input v-model="(editingTrigger as any).card_type_name" placeholder="不填表示所有类型" />
            </el-form-item>
            <el-form-item label="启用">
              <el-switch v-model="(editingTrigger as any).is_active" />
            </el-form-item>
          </el-form>
          <template #footer>
            <el-button @click="triggerDialogVisible=false">取消</el-button>
            <el-button type="primary" @click="saveTrigger">保存</el-button>
          </template>
        </el-dialog>

        <el-dialog v-model="createDialogVisible" title="新建工作流" width="420px">
          <el-form label-width="80px" size="small">
            <el-form-item label="名称">
              <el-input v-model="newWorkflowName" placeholder="请输入名称" />
            </el-form-item>
          </el-form>
          <template #footer>
            <el-button @click="createDialogVisible=false">取消</el-button>
            <el-button type="primary" @click="confirmCreate">创建</el-button>
          </template>
        </el-dialog>

        <el-drawer v-model="nodeLibVisible" title="节点库" size="360px" direction="rtl">
          <div class="node-list">
            <div class="group">
              <div class="g-title">Card</div>
              <el-card class="node-item" shadow="hover" @click="insertNode({ type:'Card.Read', params:{} })">
                <div class="n-title">Card.Read</div>
                <div class="n-desc">读取锚点/指定卡片，写入 state.card</div>
              </el-card>
              <el-card class="node-item" shadow="hover" @click="insertNode({ type:'Card.UpsertChildByTitle', params:{} })">
                <div class="n-title">Card.UpsertChildByTitle</div>
                <div class="n-desc">按标题创建/更新子卡</div>
              </el-card>
              <el-card class="node-item" shadow="hover" @click="insertNode({ type:'Card.ModifyContent', params:{} })">
                <div class="n-title">Card.ModifyContent</div>
                <div class="n-desc">设置路径或合并内容</div>
              </el-card>
            </div>
            <div class="group">
              <div class="g-title">List</div>
              <el-card class="node-item" shadow="hover" @click="insertNode({ type:'List.ForEach', params:{ listPath:'$.content.xxx' }, body:[{ type:'Card.UpsertChildByTitle', params:{} }] })">
                <div class="n-title">List.ForEach</div>
                <div class="n-desc">遍历集合并执行 body</div>
              </el-card>
              <el-card class="node-item" shadow="hover" @click="insertNode({ type:'List.ForEachRange', params:{ countPath:'$.content.count', start:1 }, body:[{ type:'Card.UpsertChildByTitle', params:{} }] })">
                <div class="n-title">List.ForEachRange</div>
                <div class="n-desc">遍历 1..N 并执行 body</div>
              </el-card>
            </div>
          </div>
        </el-drawer>
      </div>
    </div>
  </div>
  
</template>

<style scoped>
.workflow-studio { padding: 12px; background: var(--el-bg-color-page); color: var(--el-text-color-primary); }
.header { display: flex; align-items: baseline; gap: 12px; margin-bottom: 8px; }
.desc { color: var(--el-text-color-secondary); }
.layout { display: grid; grid-template-columns: 280px 1fr; gap: 12px; }
.left { border-right: 1px solid var(--el-border-color); padding-right: 8px; }
.item { display: flex; align-items: center; justify-content: space-between; width: 100%; }
.item.active { color: var(--el-color-primary); font-weight: 600; }
.item .name { font-weight: 500; }
.item .meta { color: var(--el-text-color-secondary); font-size: 12px; }
.item .tag { margin-left: 6px; color: var(--el-color-primary); }
.item .dsl { margin-left: 6px; opacity: .7; }
.toolbar { display: flex; gap: 8px; margin-bottom: 8px; }
.json { background: var(--el-fill-color-light); padding: 8px; border-radius: 6px; overflow: auto; max-height: 30vh; }
.canvas-and-panel { display: grid; grid-template-columns: 1fr auto; gap: 12px; align-items: start; }
.param-wrap { position: relative; display: grid; grid-template-columns: 1fr; }
.param-panel { border-left: 1px solid var(--el-border-color); height: 60vh; overflow: auto; }
.resizer { position: absolute; left: -6px; top: 0; bottom: 0; width: 6px; cursor: col-resize; }
.node-list { display: flex; flex-direction: column; gap: 12px; }
.group .g-title { font-weight: 600; margin: 4px 0; }
.node-item { margin-bottom: 8px; cursor: pointer; }
.node-item .n-title { font-weight: 600; }
.node-item .n-desc { color: var(--el-text-color-secondary); font-size: 12px; }
.json :deep(pre) { margin: 0; color: var(--el-text-color-primary); font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; font-size: 12px; }
.left :deep(.el-menu), .left :deep(.el-menu-item) { color: var(--el-text-color-primary); }
.ctx { position: fixed; z-index: 3000; }
.ctx-card { padding: 6px 0; }
.ctx-item { display: flex; align-items: center; gap: 6px; padding: 6px 12px; cursor: pointer; }
.ctx-item:hover { background: var(--el-fill-color-light); }
</style>


