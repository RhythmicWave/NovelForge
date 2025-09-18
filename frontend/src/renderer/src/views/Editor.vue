<template>
  <div class="editor-layout">
    <!-- 左侧卡片导航树 -->
    <el-aside class="sidebar card-navigation-sidebar" :style="{ width: leftSidebarWidth + 'px' }" @contextmenu.prevent="onSidebarContextMenu">
      <div class="sidebar-header">
        <h3 class="sidebar-title">创作卡片</h3>
        
      </div>

      <!-- 上半区（类型列表 + 自由卡片库） -->
      <div class="types-pane" :style="{ height: typesPaneHeight + 'px' }" @dragover.prevent @drop="onTypesPaneDrop">
        <div class="pane-title">已有卡片类型</div>
        <el-scrollbar class="types-scroll">
          <ul class="types-list">
            <li v-for="t in cardStore.cardTypes" :key="t.id" class="type-item" draggable="true"
                @dragstart="onTypeDragStart(t)">
              <span class="type-name">{{ t.name }}</span>
            </li>
          </ul>
        </el-scrollbar>
      </div>
      <!-- 内部分割条（垂直） -->
      <div class="inner-resizer" @mousedown="startResizingInner"></div>

      <!-- 下半区：项目卡片树 -->
      <div class="cards-pane" :style="{ height: `calc(100% - ${typesPaneHeight + innerResizerThickness}px)` }" @dragover.prevent @drop="onCardsPaneDrop">
        <div class="cards-title">
          <div class="cards-title-text">当前项目：{{ projectStore.currentProject?.name }}</div>
          <div class="cards-title-actions">
            <el-button size="small" type="primary" @click="openCreateRoot">新建卡片</el-button>
            <el-button v-if="!isFreeProject" size="small" @click="openImportFreeCards">导入卡片</el-button>
          </div>
        </div>
        <el-tree
          ref="treeRef"
          v-if="groupedTree.length > 0"
          :data="groupedTree"
          node-key="id"
          :default-expanded-keys="expandedKeys"
          :expand-on-click-node="false"
          @node-click="handleNodeClick"
          @node-expand="onNodeExpand"
          @node-collapse="onNodeCollapse"
          class="card-tree"
        >
          <template #default="{ node, data }">
            <el-dropdown class="full-row-dropdown" trigger="contextmenu" @command="(cmd:string) => handleContextCommand(cmd, data)">
              <div class="custom-tree-node full-row" draggable="true" @dragstart="onCardDragStart(data)" @dragover.prevent @drop="(e:any) => onTypeDropToNode(e, data)" @dragenter.prevent>
                <el-icon class="card-icon"> 
                  <component :is="getIconByCardType(data.card_type?.name || data.__groupType)" />
                </el-icon>
                <span class="label">{{ node.label || data.title }}</span>
                <span v-if="data.children && data.children.length > 0" class="child-count">{{ data.children.length }}</span>
              </div>
              <template #dropdown>
                <el-dropdown-menu>
                  <template v-if="!data.__isGroup">
                    <el-dropdown-item command="create-child">新建子卡片</el-dropdown-item>
                    <el-dropdown-item command="rename">重命名</el-dropdown-item>
                    <el-dropdown-item command="edit-structure">结构编辑</el-dropdown-item>
                    <el-dropdown-item command="add-as-reference">添加为引用</el-dropdown-item>
                    <el-dropdown-item command="delete" divided>删除卡片</el-dropdown-item>
                  </template>
                  <template v-else>
                    <el-dropdown-item command="delete-group" divided>删除该分组下所有卡片</el-dropdown-item>
                  </template>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
        </el-tree>
        <el-empty v-else description="暂无卡片" :image-size="80"></el-empty>
      </div>

      <!-- 空白区域右键菜单（手动触发） -->
      <span ref="blankMenuRef" class="blank-menu-ref" :style="{ position: 'fixed', left: blankMenuX + 'px', top: blankMenuY + 'px', width: '1px', height: '1px' }"></span>
      <el-dropdown v-model:visible="blankMenuVisible" trigger="manual">
        <span></span>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="openCreateRoot">新建卡片</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </el-aside>
    
    <!-- 拖拽条 -->
    <div class="resizer left-resizer" @mousedown="startResizing('left')"></div>

    <!-- 中栏主内容区 -->
    <el-main class="main-content">
      <el-tabs v-model="activeTab" type="border-card" class="main-tabs">
        <el-tab-pane label="卡片库" name="market">
          <CardMarket @edit-card="handleEditCard" />
        </el-tab-pane>
        <el-tab-pane label="编辑器" name="editor">
          <template v-if="activeCard">
            <CardEditorHost :card="activeCard" />
          </template>
          <el-empty v-else description="请从左侧选择一个卡片进行编辑" />
        </el-tab-pane>
      </el-tabs>
    </el-main>

    <!-- 右侧助手面板分隔条与面板 -->
    <div class="resizer right-resizer" @mousedown="startResizing('right')"></div>
    <el-aside class="sidebar assistant-sidebar" :style="{ width: rightSidebarWidth + 'px' }">
      <AssistantPanel
        :resolved-context="assistantResolvedContext"
        :llm-config-id="assistantParams.llm_config_id as any"
        :prompt-name="'灵感对话'"
        :temperature="assistantParams.temperature as any"
        :max_tokens="assistantParams.max_tokens as any"
        :timeout="assistantParams.timeout as any"
        :effective-schema="assistantEffectiveSchema"
        :generation-prompt-name="assistantParams.prompt_name as any"
        :current-card-title="assistantSelectionCleared ? '' : (activeCard?.title as any)"
        :current-card-content="assistantSelectionCleared ? null : (activeCard?.content as any)"
        @refresh-context="refreshAssistantContext"
        @reset-selection="resetAssistantSelection"
        @finalize="assistantFinalize"
        @jump-to-card="handleJumpToCard"
      />
    </el-aside>
  </div>

  <!-- 新建卡片对话框 -->
  <el-dialog v-model="isCreateCardDialogVisible" title="新建创作卡片" width="500px">
    <el-form :model="newCardForm" label-position="top">
      <el-form-item label="卡片标题">
        <el-input v-model="newCardForm.title" placeholder="请输入卡片标题"></el-input>
      </el-form-item>
      <el-form-item label="卡片类型">
        <el-select v-model="newCardForm.card_type_id" placeholder="请选择卡片类型" style="width: 100%">
          <el-option
            v-for="type in cardStore.cardTypes"
            :key="type.id"
            :label="type.name"
            :value="type.id"
          ></el-option>
        </el-select>
      </el-form-item>
      <el-form-item label="父级卡片 (可选)">
                <el-tree-select
           v-model="newCardForm.parent_id"
           :data="cardTree"
           :props="treeSelectProps"
           check-strictly
           :render-after-expand="false"
           placeholder="选择父级卡片"
           clearable
           style="width: 100%"
         />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="isCreateCardDialogVisible = false">取消</el-button>
      <el-button type="primary" @click="handleCreateCard">创建</el-button>
    </template>
  </el-dialog>

  <!-- 导入卡片对话框 -->
  <el-dialog v-model="importDialog.visible" title="导入卡片" width="900px" class="nf-import-dialog">
    <div style="display:flex; gap:12px; align-items:center; margin-bottom:8px; flex-wrap: wrap;">
      <el-select v-model="importDialog.sourcePid" placeholder="来源项目" style="width:220px" @change="onImportSourceChange($event as any)">
        <el-option v-for="p in importDialog.projects" :key="p.id" :label="p.name" :value="p.id" />
      </el-select>
      <el-input v-model="importDialog.search" placeholder="搜索来源卡片标题..." clearable style="flex:1; min-width: 200px" />
      <el-select v-model="importFilter.types" multiple collapse-tags placeholder="类型筛选" style="min-width:220px;" :max-collapse-tags="2">
        <el-option v-for="t in cardStore.cardTypes" :key="t.id" :label="t.name" :value="t.id!" />
      </el-select>
      <el-tree-select
        v-model="importDialog.parentId"
        :data="cardTree"
        :props="treeSelectProps"
        check-strictly
        :render-after-expand="false"
        placeholder="目标父级 (可选)"
        clearable
        popper-class="nf-tree-select-popper"
        style="width: 300px"
      />
    </div>
    <el-table :data="filteredImportCards" height="360px" border @selection-change="onImportSelectionChange">
      <el-table-column type="selection" width="48" />
      <el-table-column label="标题" prop="title" min-width="220" />
      <el-table-column label="类型" min-width="160">
        <template #default="{ row }">{{ row.card_type?.name }}</template>
      </el-table-column>
      <el-table-column label="创建时间" min-width="160">
        <template #default="{ row }">{{ (row as any).created_at }}</template>
      </el-table-column>
    </el-table>
    <template #footer>
      <el-button @click="importDialog.visible = false">取消</el-button>
      <el-button type="primary" :disabled="!selectedImportIds.length" @click="confirmImportCards">导入所选</el-button>
    </template>
  </el-dialog>

  <SchemaStudio v-model:visible="schemaStudio.visible" :mode="'card'" :target-id="schemaStudio.cardId" :context-title="schemaStudio.cardTitle" @saved="onCardSchemaSaved" />

  
</template>

<script setup lang="ts">
import { ref, onMounted, reactive, defineAsyncComponent, onBeforeUnmount, computed, watch, nextTick } from 'vue'
import { storeToRefs } from 'pinia'
import { Plus } from '@element-plus/icons-vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { 
  CollectionTag,
  MagicStick,
  ChatLineRound,
  List,
  Connection,
  Tickets,
  Notebook,
  User,
  OfficeBuilding,
  Document,
} from '@element-plus/icons-vue'
import type { components } from '@renderer/types/generated'
import { useSidebarResizer } from '@renderer/composables/useSidebarResizer'
import AssistantPanel from '@renderer/components/assistants/AssistantPanel.vue'
import { useCardStore } from '@renderer/stores/useCardStore'
import { useEditorStore } from '@renderer/stores/useEditorStore'
import { useProjectStore } from '@renderer/stores/useProjectStore'
import { useAssistantStore } from '@renderer/stores/useAssistantStore'
import SchemaStudio from '@renderer/components/shared/SchemaStudio.vue'
import { getCardSchema, createCardType } from '@renderer/api/setting'
import { getProjects } from '@renderer/api/projects'
import { getCardsForProject, copyCard, getCardAIParams } from '@renderer/api/cards'
import { generateAIContent } from '@renderer/api/ai'
 
 // Mock components that will be created later
 const CardEditorHost = defineAsyncComponent(() => import('@renderer/components/cards/CardEditorHost.vue'));
 const CardMarket = defineAsyncComponent(() => import('@renderer/components/cards/CardMarket.vue'));


 type Project = components['schemas']['ProjectRead']
 type CardRead = components['schemas']['CardRead']
 type CardCreate = components['schemas']['CardCreate']

 // 导入卡片对话框状态
 const importDialog = ref<{ visible: boolean; search: string; parentId: number | null; sourcePid: number | null; projects: Array<{id:number; name:string}> }>({ visible: false, search: '', parentId: null, sourcePid: null, projects: [] })
 const importSourceCards = ref<CardRead[]>([])
 const selectedImportIds = ref<number[]>([])
 
 // 过滤：类型 + 标题
 const importFilter = ref<{ types: number[] }>({ types: [] })
 
 const filteredImportCards = computed(() => {
   const q = (importDialog.value.search || '').trim().toLowerCase()
   let list = importSourceCards.value || []
   if (importFilter.value.types.length) {
     const typeSet = new Set(importFilter.value.types)
     list = list.filter(c => c.card_type?.id && typeSet.has(c.card_type.id))
   }
   if (q) {
     list = list.filter(c => (c.title || '').toLowerCase().includes(q))
   }
   return list
 })

 async function openImportFreeCards() {
   try {
     const list = await getProjects()
     const currentId = projectStore.currentProject?.id
     importDialog.value.projects = (list || []).filter(p => p.id !== currentId).map(p => ({ id: p.id!, name: p.name! }))
     importDialog.value.sourcePid = importDialog.value.projects[0]?.id ?? null
     selectedImportIds.value = []
     await onImportSourceChange(importDialog.value.sourcePid as any)
     importDialog.value.visible = true
   } catch { ElMessage.error('加载来源项目失败') }
 }

 async function onImportSourceChange(pid: number | null) {
   importSourceCards.value = []
   if (!pid) return
   try { importSourceCards.value = await getCardsForProject(pid) } catch { importSourceCards.value = [] }
 }

 function onImportSelectionChange(rows: any[]) {
   selectedImportIds.value = (rows || []).map(r => Number(r.id)).filter(n => Number.isFinite(n))
 }

 async function confirmImportCards() {
   try {
     const pid = projectStore.currentProject?.id
     if (!pid) return
     const targetParent = importDialog.value.parentId || null
     for (const id of selectedImportIds.value) {
       await copyCard(id, { target_project_id: pid, parent_id: targetParent as any })
     }
     await cardStore.fetchCards(pid)
     ElMessage.success('已导入所选卡片')
     importDialog.value.visible = false
   } catch { ElMessage.error('导入失败') }
 }

 // Props
 const props = defineProps<{
   initialProject: Project
 }>()

 // Store
 const cardStore = useCardStore()
 const { cardTree, activeCard, cards } = storeToRefs(cardStore)
 const editorStore = useEditorStore()
 const { expandedKeys } = storeToRefs(editorStore)
 const projectStore = useProjectStore()
 const assistantStore = useAssistantStore()
 const isFreeProject = computed(() => (projectStore.currentProject?.name || '') === '__free__')

  // --- 前端自动分组器 ---
 // 设计（新）：当某节点的直接子卡片中，任一“类型的数量 > 2”时，为该类型创建一个虚拟分组节点；
 // 其余数量 <= 2 的类型保持原样显示（即使整个父节点下只有一种类型，只要该类型数量>2也要分组）。
 // 该结构完全在前端进行，不影响后端数据
 interface TreeNode { id: number | string; title: string; children?: TreeNode[]; card_type?: { name: string }; __isGroup?: boolean; __groupType?: string }


 function buildGroupedNodes(nodes: any[]): any[] {
  return nodes.map(n => {
    const node: TreeNode = { ...n }
    // 分组节点自身不再参与分组逻辑，直接递归其子节点
    if ((n as any).__isGroup) {
      if (Array.isArray(n.children) && n.children.length > 0) {
        node.children = buildGroupedNodes(n.children as any)
      }
      return node
    }
    if (Array.isArray(n.children) && n.children.length > 0) {
      // 统计子节点类型数量
      const byType: Record<string, any[]> = {}
      n.children.forEach((c: any) => {
        const typeName = c.card_type?.name || '未知类型'
        if (!byType[typeName]) byType[typeName] = []
        byType[typeName].push(c)
      })
      const types = Object.keys(byType)
        const grouped: any[] = []
        types.forEach(t => {
          const list = byType[t]
        if (list.length > 2) {
            // 创建虚拟分组节点（id 使用字符串避免冲突）
            grouped.push({
              id: `group:${n.id}:${t}`,
              title: `${t}`,
              __isGroup: true,
              __groupType: t,
              children: list.map(x => ({ ...x }))
            })
          } else {
          // 数量为 1 或 2，直接平铺
          grouped.push(...list)
          }
        })
      // 递归对子树继续处理（分组节点与普通节点都递归其 children）
      node.children = grouped.map((x: any) => {
        const copy = { ...x }
        if (Array.isArray(copy.children) && copy.children.length > 0) {
          copy.children = buildGroupedNodes(copy.children as any)
        }
        return copy
      })
    }
    return node
  })
}

// 基于原始 cardTree 计算带分组的树
const groupedTree = computed(() => buildGroupedNodes(cardTree.value as unknown as any[]))

// Local State
const activeTab = ref('market')
const isCreateCardDialogVisible = ref(false)
const newCardForm = reactive<Partial<CardCreate>>({
  title: '',
  card_type_id: undefined,
  parent_id: '' as any
})

// 空白区域菜单状态
const blankMenuVisible = ref(false)
const blankMenuX = ref(0)
const blankMenuY = ref(0)
const blankMenuRef = ref<HTMLElement | null>(null)

// Composables
  const { leftSidebarWidth, rightSidebarWidth, startResizing } = useSidebarResizer()
  
 // 统一 TreeSelect 样式/属性，确保选项可见
 const treeSelectProps = {
   value: 'id',
   label: 'title',
   children: 'children'
 } as const
 
 // 内部垂直分割：类型/卡片高度
 const typesPaneHeight = ref(180)
 const innerResizerThickness = 6
 // 左侧宽度拖拽沿用 useSidebarResizer.startResizing('left')

 function startResizingInner() {
   const startY = (event as MouseEvent).clientY
   const startH = typesPaneHeight.value
   const onMove = (e: MouseEvent) => {
     const dy = e.clientY - startY
     const next = Math.max(120, Math.min(startH + dy, 400))
     typesPaneHeight.value = next
   }
   const onUp = () => {
     window.removeEventListener('mousemove', onMove)
     window.removeEventListener('mouseup', onUp)
   }
   window.addEventListener('mousemove', onMove)
   window.addEventListener('mouseup', onUp)
 }

// 拖拽：从类型到卡片区域创建新实例
function onTypeDragStart(t: any) {
  try { (event as DragEvent).dataTransfer?.setData('application/x-card-type-id', String(t.id)) } catch {}
}
async function onCardsPaneDrop(e: DragEvent) {
 try {
   const typeId = e.dataTransfer?.getData('application/x-card-type-id')
   if (typeId) {
     // 在根创建一个该类型的新卡片，标题默认与类型同名（可后续弹框重命名）
     newCardForm.title = (cardStore.cardTypes.find(ct => ct.id === Number(typeId))?.name || '新卡片')
     newCardForm.card_type_id = Number(typeId)
     newCardForm.parent_id = '' as any
     handleCreateCard()
     return
   }
   // 优先处理从 __free__ 跨项目拖拽复制
   const freeCardId = e.dataTransfer?.getData('application/x-free-card-id')
   if (freeCardId) {
     await copyCard(Number(freeCardId), { target_project_id: projectStore.currentProject!.id, parent_id: null as any })
     await cardStore.fetchCards(projectStore.currentProject!.id)
     ElMessage.success('已复制自由卡片到根目录')
     return
   }
   // 其次处理同项目移动到根
   const movedCardId = e.dataTransfer?.getData('application/x-card-id')
   if (movedCardId) {
     // 设为根
     await cardStore.modifyCard(Number(movedCardId), { parent_id: null, display_order: 999999 }, { skipHooks: true })
     return
   }
 } catch {}
}

// 从卡片实例提升为类型：在上半区松手
async function onTypesPaneDrop(e: DragEvent) {
 try {
   const cardIdStr = e.dataTransfer?.getData('application/x-card-id')
   const cardId = cardIdStr ? Number(cardIdStr) : NaN
   if (!cardId || Number.isNaN(cardId)) return
   // 读取该卡片的有效 schema
   const resp = await getCardSchema(cardId)
   const effective = resp?.effective_schema || resp?.json_schema
   if (!effective) { ElMessage.warning('该卡片暂无可用结构，无法生成类型'); return }
   // 默认名称：卡片标题或“新类型”
   const old = cards.value.find(c => (c as any).id === cardId)
   const defaultName = (old?.title || '新类型') as string
   const { value } = await ElMessageBox.prompt('从该实例创建卡片类型，请输入类型名称：', '创建卡片类型', {
     inputValue: defaultName,
     confirmButtonText: '创建',
     cancelButtonText: '取消',
     inputValidator: (v:string) => v.trim().length > 0 || '名称不能为空'
   })
   const finalName = String(value).trim()
   await createCardType({ name: finalName, description: `${finalName}的默认卡片类型`, json_schema: effective } as any)
   ElMessage.success('已从实例创建卡片类型')
   await cardStore.fetchCardTypes()
 } catch (err) {
   // 用户取消或错误忽略
 }
}

// 从卡片到类型区域：派生为新类型（稍后实现完整流程）
function onCardDragStart(card: any) {
 try { (event as DragEvent).dataTransfer?.setData('application/x-card-id', String(card?.id || '')) } catch {}
 // 若当前项目是 __free__，同时写入自由卡专用的拖拽数据，便于跨项目复制
 try {
   const isFree = (projectStore.currentProject?.name || '') === '__free__'
   if (isFree && card?.id) {
     (event as DragEvent).dataTransfer?.setData('application/x-free-card-id', String(card.id))
   }
 } catch {}
}


 // --- 拖拽：从类型列表到卡片树 ---
function getDraggedTypeId(e: DragEvent): number | null {
 try {
   const raw = e.dataTransfer?.getData('application/x-card-type-id') || ''
   const n = Number(raw)
   return Number.isFinite(n) && n > 0 ? n : null
 } catch { return null }
}

async function onTypeDropToNode(e: DragEvent, nodeData: any) {
 const typeId = getDraggedTypeId(e)
 if (typeId) {
   // 仅对真实卡片节点生效，分组节点不接收
   if (nodeData?.__isGroup) return
   await cardStore.addCard({ title: '新建卡片', card_type_id: typeId, parent_id: nodeData?.id } as any)
   return
 }
 try {
   // 优先处理从 __free__ 跨项目拖拽复制
   const freeCardId = e.dataTransfer?.getData('application/x-free-card-id')
   if (freeCardId) {
     if (nodeData?.__isGroup) return
     await copyCard(Number(freeCardId), { target_project_id: projectStore.currentProject!.id, parent_id: Number(nodeData?.id) })
     await cardStore.fetchCards(projectStore.currentProject!.id)
     ElMessage.success('已复制自由卡片到该节点下')
     return
   }
   const movedCardId = e.dataTransfer?.getData('application/x-card-id')
   if (movedCardId) {
     if (nodeData?.__isGroup) return
     await cardStore.modifyCard(Number(movedCardId), { parent_id: Number(nodeData?.id) }, { skipHooks: true })
     return
   }
 } catch {}
}

 // --- Methods ---

 // 点击行为对“分组节点”不做打开编辑，仅用于展开/折叠。对实际卡片才触发编辑。
 function handleNodeClick(data: any) {
  if (data.__isGroup) return
  // 若是章节正文，默认在专注窗打开
  if (data?.card_type?.name === '章节正文' && projectStore.currentProject?.id) {
    // @ts-ignore
    window.api?.openChapterStudio?.(projectStore.currentProject.id, data.id)
    return
  }
  cardStore.setActiveCard(data.id)
  assistantSelectionCleared.value = false
  activeTab.value = 'editor'
  try {
    const pid = projectStore.currentProject?.id as number
    const pname = projectStore.currentProject?.name || ''
    const full = (cards.value || []).find((c:any) => c.id === data.id)
    const title = (full?.title || data.title || '') as string
    const content = (full?.content || (data as any).content || {})
    if (pid && data?.id) {
      // 仅追加 auto 引用：store 规则会保留已存在的 manual，不会被 auto 覆盖
      assistantStore.addAutoRef({ projectId: pid, projectName: pname, cardId: data.id, cardTitle: title, content })
    }
  } catch {}
}

// 兜底：当 activeCard 改变时也自动注入一次
watch(activeCard, (c) => {
 try {
   if (!c) return
   const pid = projectStore.currentProject?.id as number
   const pname = projectStore.currentProject?.name || ''
   assistantStore.addAutoRef({ projectId: pid, projectName: pname, cardId: (c as any).id, cardTitle: (c as any).title || '', content: (c as any).content || {} })
 } catch {}
})

function onNodeExpand(_: any, node: any) {
  editorStore.addExpandedKey(String(node.key))
}

function onNodeCollapse(_: any, node: any) {
  editorStore.removeExpandedKey(String(node.key))
}

function handleEditCard(cardId: number) {
  cardStore.setActiveCard(cardId);
  activeTab.value = 'editor';
}

async function handleCreateCard() {
  if (!newCardForm.title || !newCardForm.card_type_id) {
    ElMessage.warning('请填写卡片标题和类型');
    return;
  }
  const payload: any = {
    ...newCardForm,
    parent_id: (newCardForm as any).parent_id === '' ? undefined : (newCardForm as any).parent_id
  }
  await cardStore.addCard(payload as CardCreate);
  isCreateCardDialogVisible.value = false;
  // Reset form
  Object.assign(newCardForm, { title: '', card_type_id: undefined, parent_id: '' as any });
}

// 根据卡片类型返回图标组件
function getIconByCardType(typeName?: string) {
  // 约定：若后端默认类型名称变更，可在此映射中调整
  switch (typeName) {
    case '作品标签':
      return CollectionTag
    case '金手指':
      return MagicStick
    case '一句话梗概':
      return ChatLineRound
    case '故事大纲':
      return List
    case '世界观设定':
      return Connection
    case '核心蓝图':
      return Tickets
    case '分卷大纲':
      return Notebook
    case '章节大纲':
      return Document
    case '角色卡':
      return User
    case '场景卡':
      return OfficeBuilding
    default:
      return Document // 通用默认图标
  }
}

// 右键菜单命令处理（新建子卡片、删除卡片）
function handleContextCommand(command: string, data: any) {
  if (command === 'create-child') {
    openCreateChild(data.id)
  } else if (command === 'delete') {
    deleteNode(data.id, data.title)
  } else if (command === 'delete-group') {
    deleteGroupNodes(data)
  } else if (command === 'edit-structure') {
     if (!data?.id || data.__isGroup) return
     openCardSchemaStudio(data)
  } else if (command === 'rename') {
    if (!data?.id || data.__isGroup) return
    renameCard(data.id, data.title || '')
  } else if (command === 'add-as-reference') {
    try {
      if (!data?.id || data.__isGroup) return
      const pid = projectStore.currentProject?.id as number
      const pname = projectStore.currentProject?.name || ''
      const full = (cards.value || []).find((c:any) => c.id === data.id)
      const title = (full?.title || data.title || '') as string
      const content = (full?.content || (data as any).content || {})
      assistantStore.addInjectedRefDirect({ projectId: pid, projectName: pname, cardId: data.id, cardTitle: title, content }, 'manual')
      ElMessage.success('已添加为引用')
    } catch {}
  }
}

function openCardSchemaStudio(card: any) {
  schemaStudio.value = { visible: true, cardId: card.id, cardTitle: card.title || '' }
}

const schemaStudio = ref<{ visible: boolean; cardId: number; cardTitle: string }>({ visible: false, cardId: 0, cardTitle: '' })

async function onCardSchemaSaved() {
  try {
    await cardStore.fetchCards(projectStore.currentProject?.id as number)
  } catch {}
}

// 打开“新建卡片”对话框并预填父ID
function openCreateChild(parentId: number) {
  newCardForm.title = ''
  newCardForm.card_type_id = undefined
  newCardForm.parent_id = parentId as any
  isCreateCardDialogVisible.value = true
}

function openCreateRoot() {
  newCardForm.title = ''
  newCardForm.card_type_id = undefined
  newCardForm.parent_id = '' as any
  isCreateCardDialogVisible.value = true
  blankMenuVisible.value = false
}

// 空白处右键：仅当未命中节点时显示菜单
function onSidebarContextMenu(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (target.closest('.custom-tree-node')) return
  blankMenuX.value = e.clientX
  blankMenuY.value = e.clientY
  blankMenuVisible.value = true
}

// 删除卡片（确认）
async function deleteNode(cardId: number, title: string) {
  try {
    await ElMessageBox.confirm(`确认删除卡片「${title}」？此操作不可恢复`, '删除确认', { type: 'warning' })
    await cardStore.removeCard(cardId)
  } catch (e) {
    // 用户取消
  }
}

async function deleteGroupNodes(groupData: any) {
  try {
    const title = groupData?.title || groupData?.__groupType || '该分组'
    await ElMessageBox.confirm(`确认删除${title}下的所有卡片？此操作不可恢复`, '删除确认', { type: 'warning' })
    const directChildren: any[] = Array.isArray(groupData?.children) ? groupData.children : []
    const toDeleteOrdered: number[] = []

    // 递归收集：叶子优先（先删子孙，再删父）
    function collectDescendantIds(parentId: number) {
      const childIds = (cards.value || []).filter((c: any) => c.parent_id === parentId).map((c: any) => c.id)
      for (const cid of childIds) collectDescendantIds(cid)
      toDeleteOrdered.push(parentId)
    }

    for (const child of directChildren) {
      collectDescendantIds(child.id)
    }

    // 去重（理论上无交叉）
    const seen = new Set<number>()
    for (const id of toDeleteOrdered) {
      if (seen.has(id)) continue
      seen.add(id)
      await cardStore.removeCard(id)
    }
  } catch (e) {
    // 用户取消
  }
}

// 重命名功能
async function renameCard(cardId: number, oldTitle: string) {
  try {
    const { value } = await ElMessageBox.prompt('重命名会立即生效，请输入新名称：', '重命名', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputValue: oldTitle,
      inputPlaceholder: '请输入卡片标题',
      inputValidator: (v:string) => v.trim().length > 0 || '标题不能为空'
    })
    const newTitle = String(value).trim()
    if (newTitle === oldTitle) return
    await cardStore.modifyCard(cardId, { title: newTitle })
    ElMessage.success('已重命名')
  } catch {
    // 用户取消或失败
  }
}

// 助手面板上下文
const assistantResolvedContext = ref<string>('')
const assistantEffectiveSchema = ref<any>(null)
const assistantSelectionCleared = ref<boolean>(false)
const assistantParams = ref<{ llm_config_id: number | null; prompt_name: string | null; temperature: number | null; max_tokens: number | null; timeout: number | null }>({ llm_config_id: null, prompt_name: '灵感对话', temperature: null, max_tokens: null, timeout: null })

async function refreshAssistantContext() {
  try {
    const card = assistantSelectionCleared.value ? null : (activeCard.value as any)
    if (!card) { assistantResolvedContext.value = ''; assistantEffectiveSchema.value = null; return }
    // 计算上下文（沿用 contextResolver）
    const { resolveTemplate } = await import('@renderer/services/contextResolver')
    // 使用卡片当前保存的 ai_context_template 和 content
    const resolved = resolveTemplate({ template: card.ai_context_template || '', cards: cards.value, currentCard: card })
    assistantResolvedContext.value = resolved
    // 读取有效 Schema
    const resp = await getCardSchema(card.id)
    assistantEffectiveSchema.value = resp?.effective_schema || resp?.json_schema || null
    // 读取有效 AI 参数（保障 llm_config_id 存在）
    try {
      const ai = await getCardAIParams(card.id)
      const eff = (ai?.effective_params || {}) as any
      assistantParams.value = {
        llm_config_id: eff.llm_config_id ?? null,
        prompt_name: (eff.prompt_name ?? '灵感对话') as any,
        temperature: eff.temperature ?? null,
        max_tokens: eff.max_tokens ?? null,
        timeout: eff.timeout ?? null,
      }
    } catch {
      // 回退：直接使用卡片上的 ai_params
      const p = (card?.ai_params || {}) as any
      assistantParams.value = {
        llm_config_id: p.llm_config_id ?? null,
        prompt_name: (p.prompt_name ?? '灵感对话') as any,
        temperature: p.temperature ?? null,
        max_tokens: p.max_tokens ?? null,
        timeout: p.timeout ?? null,
      }
    }
  } catch { assistantResolvedContext.value = '' }
}

watch(activeCard, () => { if (!assistantSelectionCleared.value) refreshAssistantContext() })

function resetAssistantSelection() {
  assistantSelectionCleared.value = true
  assistantResolvedContext.value = ''
  assistantEffectiveSchema.value = null
}

const assistantFinalize = async (summary: string) => {
  try {
    const card = activeCard.value as any
    if (!card) return
    const evt = new CustomEvent('nf:assistant-finalize', { detail: { cardId: card.id, summary } })
    window.dispatchEvent(evt)
    ElMessage.success('已发送定稿要点到编辑器页')
  } catch {}
}

async function onAssistantFinalize(e: CustomEvent) {
  try {
    const card = activeCard.value as any
    if (!card) return
    const summary: string = (e as any)?.detail?.summary || ''
    const llmId = assistantParams.value.llm_config_id
    const promptName = (assistantParams.value.prompt_name || '内容生成') as string
    const schema = assistantEffectiveSchema.value
    if (!llmId) { ElMessage.warning('请先为该卡片选择模型'); return }
    if (!schema) { ElMessage.warning('未获取到有效 Schema，无法定稿'); return }
    // 组装定稿输入：上下文 + 定稿要点
    const ctx = (assistantResolvedContext.value || '').trim()
    const inputText = [ctx ? `【上下文】\n${ctx}` : '', summary ? `【定稿要点】\n${summary}` : ''].filter(Boolean).join('\n\n')
    const result = await generateAIContent({
      input: { input_text: inputText },
      llm_config_id: llmId as any,
      prompt_name: promptName,
      response_model_schema: schema as any,
      temperature: assistantParams.value.temperature ?? undefined,
      max_tokens: assistantParams.value.max_tokens ?? undefined,
      timeout: assistantParams.value.timeout ?? undefined,
    } as any)
    if (result) {
      await cardStore.modifyCard(card.id, { content: result as any })
      ElMessage.success('已根据要点生成并写回该卡片')
    } else {
      ElMessage.error('定稿生成失败：无返回内容')
    }
  } catch (err) {
    ElMessage.error('定稿生成失败')
    console.error(err)
  }
}

// 助手 chips 跳转卡片
async function handleJumpToCard(payload: { projectId: number; cardId: number }) {
  try {
    const curPid = projectStore.currentProject?.id
    if (curPid !== payload.projectId) {
      // 切换项目：从全部项目列表中找到目标项目并设置
      const all = await getProjects()
      const target = (all || []).find(p => p.id === payload.projectId)
      if (target) {
        projectStore.setCurrentProject(target as any)
        await cardStore.fetchCards(target.id!)
      }
    }
    // 激活目标卡（仅导航，不改动 injectedRefs）
    cardStore.setActiveCard(payload.cardId)
    activeTab.value = 'editor'
  } catch {}
}

// --- Lifecycle ---

onMounted(async () => {
  // Fetch initial data for the card system (like types and models)
  // Cards will be fetched automatically by the watcher in the card store
  await cardStore.fetchInitialData()
  // 进入编辑页时也刷新一次可用模型（处理应用在其他页新增模型的场景）
  await cardStore.fetchAvailableModels()
  window.addEventListener('nf:navigate', onNavigate as any)
  window.addEventListener('nf:assistant-finalize', onAssistantFinalize as any)
  await refreshAssistantContext()
})

 onBeforeUnmount(() => {
   window.removeEventListener('nf:navigate', onNavigate as any)
   window.removeEventListener('nf:assistant-finalize', onAssistantFinalize as any)
 })

 function onNavigate(e: CustomEvent) {
   if ((e as any).detail?.to === 'market') {
     activeTab.value = 'market'
   }
 }

 // 点击页面任意处隐藏空白菜单
 document.addEventListener('click', () => (blankMenuVisible.value = false))

 const treeRef = ref<any>(null)

 watch(groupedTree, async () => {
   await nextTick()
   try { treeRef.value?.setExpandedKeys?.(expandedKeys) } catch {}
 }, { deep: true })
</script>

<style scoped>
/* 让右键触发区域充满整行 */
.full-row-dropdown { display: block; width: 100%; }
.blank-menu-ref { pointer-events: none; }

.editor-layout {
  display: flex;
  height: 100%;
  width: 100%;
  position: relative;
  background-color: var(--el-bg-color-page);
}

.sidebar {
  display: flex;
  flex-direction: column;
  background-color: var(--el-bg-color);
  transition: width 0.2s;
  flex-shrink: 0;
  overflow: hidden;
  border-right: 1px solid var(--el-border-color-light);
}

.card-navigation-sidebar {
  padding: 8px;
}

/* 顶部标题区已移除按钮，这里直接隐藏以消除空隙 */
.sidebar-header { display: none; }

.sidebar-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.card-tree {
  background-color: transparent;
  flex-grow: 1;
  overflow-y: auto;
}

.custom-tree-node {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 6px;
  font-size: 14px;
  padding-right: 8px;
}
.card-icon {
  color: var(--el-text-color-secondary);
}
.child-count {
  margin-left: auto;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.resizer {
  width: 5px;
  background: transparent;
  cursor: col-resize;
  z-index: 10;
  user-select: none;
  position: relative;
  transition: background-color 0.2s;
}
.resizer:hover {
  background: var(--el-color-primary-light-7);
}

.main-content {
  padding: 0;
  display: flex;
  flex-direction: column;
}

.main-tabs {
  flex-grow: 1;
  display: flex;
  flex-direction: column;
}

:deep(.el-tabs__content) {
  flex-grow: 1;
  overflow-y: auto;
}
:deep(.el-tab-pane) {
  height: 100%;
}

.custom-tree-node.full-row { 
  display: flex;
  align-items: center;
  width: 100%;
  padding: 3px 6px;
}
.custom-tree-node.full-row .label {
  flex: 1;
}


.types-pane { display: flex; flex-direction: column; border-bottom: 1px solid var(--el-border-color-light); background: var(--el-fill-color-lighter); padding: 6px; box-shadow: 0 2px 6px -2px var(--el-box-shadow-lighter); border-radius: 6px; }
.pane-title { font-size: 12px; color: var(--el-text-color-regular); font-weight: 600; padding: 2px 4px 6px 4px; }
.types-scroll { flex: 1; background: var(--el-fill-color-lighter); }
.types-list { list-style: none; padding: 0; margin: 0; }
.type-item { padding: 6px 8px; cursor: grab; display: flex; align-items: center; color: var(--el-text-color-primary); font-size: 13px; border-radius: 4px; }
.type-item:hover { background: var(--el-fill-color-light); color: var(--el-color-primary); }
.type-name { flex: 1; }

.inner-resizer { height: 6px; cursor: row-resize; background: var(--el-fill-color-light); border-top: 1px solid var(--el-border-color-light); border-bottom: 1px solid var(--el-border-color-light); transition: height .12s ease, background-color .12s ease, border-color .12s ease; }
.inner-resizer:hover { height: 8px; background: var(--el-fill-color); border-top: 1px solid var(--el-border-color); border-bottom: 1px solid var(--el-border-color); }
/* 下半区：标题置顶并设置滚动容器 */
.cards-pane { position: relative; padding-top: 8px; overflow: auto; }
.cards-title { position: sticky; top: 0; z-index: 1; display: flex; flex-direction: column; align-items: flex-start; gap: 6px; font-size: 13px; font-weight: 600; color: var(--el-text-color-regular); padding: 6px 6px; background: var(--el-bg-color); border-bottom: 1px dashed var(--el-border-color-light); margin-bottom: 6px; }
.cards-title-text { width: 100%; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cards-title-actions { display: flex; align-items: center; gap: 6px; }
.assistant-sidebar { border-left: 1px solid var(--el-border-color-light); background: var(--el-bg-color); flex-shrink: 0; }
.right-resizer { cursor: col-resize; width: 5px; background: transparent; }
.right-resizer:hover { background: var(--el-color-primary-light-7); }
.nf-import-dialog :deep(.el-input__wrapper) { font-size: 14px; }
.nf-import-dialog :deep(.el-input__inner) { font-size: 14px; }
.nf-import-dialog :deep(.el-table .cell) { font-size: 14px; color: var(--el-text-color-primary); }
.nf-import-dialog :deep(.el-table__row) { height: 40px; }
.nf-tree-select-popper { min-width: 320px; }
.nf-tree-select-popper { background: var(--el-bg-color-overlay, #fff); color: var(--el-text-color-primary); }
.nf-tree-select-popper :deep(.el-select-dropdown__item) { color: var(--el-text-color-primary); }
.nf-tree-select-popper :deep(.el-tree) { background: transparent; }
.nf-tree-select-popper :deep(.el-tree-node__content) { background: transparent; }
.nf-tree-select-popper :deep(.el-tree-node__label) { font-size: 14px; color: var(--el-text-color-primary); }
.nf-tree-select-popper :deep(.is-current > .el-tree-node__content),
.nf-tree-select-popper :deep(.el-tree-node__content:hover) { background: var(--el-fill-color-light); }
</style>