<template>
  <div class="editor-layout">
    <!-- 左侧卡片导航树 -->
    <el-aside class="sidebar card-navigation-sidebar" :style="{ width: leftSidebarDisplayWidth + 'px' }" @contextmenu.prevent="onSidebarContextMenu">
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
            <el-button size="small" @click="openExportDialog">导出卡片</el-button>
            <el-button v-if="selectedCardIds.length > 0" size="small" type="danger" @click="batchDeleteCards">
              删除选中 ({{ selectedCardIds.length }})
            </el-button>
          </div>
        </div>
        
        <!-- 搜索框 -->
        <div class="search-box" style="padding: 0 8px 8px;">
           <el-input 
             v-model="searchQuery" 
             placeholder="搜索卡片..." 
             :prefix-icon="Search"
             clearable
             @input="handleSearch"
           />
        </div>

        <!-- 搜索结果 -->
        <div v-if="isSearching" class="search-results-list" v-loading="searchLoading">
           <div 
             v-for="card in searchResults" 
             :key="card.id" 
             class="search-item" 
             @click="handleNodeClick({ id: card.id, title: card.title, card_type: card.card_type })"
           >
              <el-icon class="card-icon"><component :is="getIconByCardType(card.card_type?.name)" /></el-icon>
              <span class="search-item-title">{{ card.title }}</span>
           </div>
           <el-empty v-if="!searchLoading && searchResults.length === 0" description="无搜索结果" :image-size="60" />
        </div>

        <template v-else>
          <el-tree
            v-if="groupedTree.length > 0"
            ref="treeRef"
            :data="groupedTree"
            node-key="id"
            :default-expanded-keys="expandedKeys"
            :expand-on-click-node="false"
            @node-click="handleNodeClick"
            @node-expand="onNodeExpand"
            @node-collapse="onNodeCollapse"
            draggable
            :allow-drop="handleAllowDrop"
            :allow-drag="handleAllowDrag"
            @node-drop="handleNodeDrop"
            class="card-tree"
          >
            <template #default="{ node, data }">
              <el-dropdown class="full-row-dropdown" trigger="contextmenu" @command="(cmd:string) => handleContextCommand(cmd, data)">
                <div 
                  class="custom-tree-node full-row" 
                  :class="{ 'selected': isCardSelected(data.id) }"
                  @click.stop="handleCardClick($event, data)"
                  @dragover.prevent 
                  @drop="(e:any) => onExternalDropToNode(e, data)" 
                  @dragenter.prevent
                >
                  <el-icon class="card-icon"> 
                    <component :is="getIconByCardType(data.card_type?.name || data.__groupType)" />
                  </el-icon>
                  <span class="label">{{ node.label || data.title }}</span>
                  <span v-if="data.children && data.children.length > 0" class="child-count">{{ data.children.length }}</span>
                </div>
                <template #dropdown>
                  <el-dropdown-menu>
                    <template v-if="!data.__isGroup">
                      <el-dropdown-item command="create-child" :disabled="selectedCardIds.length > 1">新建子卡片</el-dropdown-item>
                      <el-dropdown-item command="rename" :disabled="selectedCardIds.length > 1">重命名</el-dropdown-item>
                      <el-dropdown-item command="edit-structure" :disabled="selectedCardIds.length > 1">结构编辑</el-dropdown-item>
                      <el-dropdown-item command="add-as-reference" :disabled="selectedCardIds.length > 1">添加为引用</el-dropdown-item>
                      <el-dropdown-item v-if="selectedCardIds.length > 1" command="batch-delete" divided>删除选中的卡片 ({{ selectedCardIds.length }})</el-dropdown-item>
                      <el-dropdown-item v-else command="delete" divided>删除卡片</el-dropdown-item>
                    </template>
                    <template v-else>
                      <el-dropdown-item command="create-child-in-group">新建子卡片</el-dropdown-item>
                      <el-dropdown-item command="delete-group" divided>删除该分组下所有卡片</el-dropdown-item>
                    </template>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </template>
          </el-tree>
          <el-empty v-else description="暂无卡片" :image-size="80"></el-empty>
        </template>
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
    <div v-if="isLeftSidebarVisible" class="resizer left-resizer" @mousedown="startResizing('left')"></div>

    <!-- 中栏主内容区 -->
    <el-main class="main-content">
      <el-tabs v-model="activeTab" type="border-card" class="main-tabs">
        <el-tab-pane label="卡片库" name="market">
          <CardMarket @edit-card="handleEditCard" />
        </el-tab-pane>
        <el-tab-pane label="编辑器" name="editor">
          <template v-if="activeCard">
            <CardEditorHost :card="activeCard" :prefetched="prefetchedContext" />
          </template>
          <el-empty v-else description="请从左侧选择一个卡片进行编辑" />
        </el-tab-pane>
        <el-tab-pane label="关系图管理" name="relation-graph">
          <RelationGraphPanel :refresh-seq="relationGraphRefreshSeq" />
        </el-tab-pane>
      </el-tabs>
    </el-main>

    <!-- 右侧助手面板分隔条与面板 -->
    <div class="resizer right-resizer" @mousedown="startResizing('right')"></div>
    <el-aside class="sidebar assistant-sidebar" :style="{ width: rightSidebarWidth + 'px' }">
      <!-- 章节正文卡片：显示4个Tab -->
      <template v-if="showRightSidebarTabs">
        <el-tabs v-model="activeRightTab" type="card" class="right-tabs">
          <el-tab-pane label="助手" name="assistant">
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
          </el-tab-pane>
          
          <template v-if="isChapterContent">
          <el-tab-pane label="参与实体" name="context">
            <ContextPanel 
              :project-id="projectStore.currentProject?.id"
              :prefetched="prefetchedContext"
              :volume-number="chapterVolumeNumber"
              :chapter-number="chapterChapterNumber"
              :participants="chapterParticipants"
              @update:participants="handleContextParticipantsUpdate"
              @context-updated="handleContextAssembledUpdate"
            />
          </el-tab-pane>
          
          <el-tab-pane label="提取" name="extract">
            <ChapterToolsPanel />
          </el-tab-pane>
          
          <el-tab-pane label="大纲" name="outline">
            <OutlinePanel 
              :active-card="activeCard"
              :volume-number="chapterVolumeNumber"
              :chapter-number="chapterChapterNumber"
            />
          </el-tab-pane>
          </template>
          
          <el-tab-pane label="审核结果" name="review-history">
            <ReviewHistoryPanel
              :target-card-id="reviewTargetCardIdForSidebar"
            />
          </el-tab-pane>
        </el-tabs>
      </template>
      
      <!-- 其他卡片：仅显示助手 -->
      <AssistantPanel
        v-else
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
    <el-button class="left-sidebar-toggle" type="primary" size="small" @click="toggleLeftSidebar">
      {{ isLeftSidebarVisible ? '隐藏导航' : '显示导航' }}
    </el-button>
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
  <CardExportDialog
    v-model="exportDialogVisible"
    :project-id="projectStore.currentProject?.id"
    :project-name="projectStore.currentProject?.name"
    :cards="cards as any"
    :card-types="cardStore.cardTypes as any"
    :initial-card-id="selectedCardIds.length === 1 ? selectedCardIds[0] : ((activeCard as any)?.id ?? null)"
  />

  
</template>

<script setup lang="ts">
import { ref, onMounted, reactive, defineAsyncComponent, onBeforeUnmount, computed, watch, nextTick } from 'vue'
import { storeToRefs } from 'pinia'
import { Plus, Search } from '@element-plus/icons-vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { debounce } from 'lodash-es'
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
  Folder,
} from '@element-plus/icons-vue'
import type { components } from '@renderer/types/generated'
import { useSidebarResizer } from '@renderer/composables/useSidebarResizer'
import AssistantPanel from '@renderer/components/assistants/AssistantPanel.vue'
import ContextPanel from '@renderer/components/panels/ContextPanel.vue'
import ChapterToolsPanel from '@renderer/components/panels/ChapterToolsPanel.vue'
import OutlinePanel from '@renderer/components/panels/OutlinePanel.vue'
import ReviewHistoryPanel from '@renderer/components/panels/ReviewHistoryPanel.vue'
import RelationGraphPanel from '@renderer/components/panels/RelationGraphPanel.vue'
import { useCardStore } from '@renderer/stores/useCardStore'
import { useEditorStore } from '@renderer/stores/useEditorStore'
import { useProjectStore } from '@renderer/stores/useProjectStore'
import { useAssistantStore } from '@renderer/stores/useAssistantStore'
import SchemaStudio from '@renderer/components/shared/SchemaStudio.vue'
import { getCardSchema, createCardType } from '@renderer/api/setting'
import { getProjects } from '@renderer/api/projects'
import { getCardsForProject, copyCard, getCardAIParams, searchCards } from '@renderer/api/cards'
import { generateAIContent } from '@renderer/api/ai'
import type { AssistantRef, ChapterExcerptRef, ReviewResultRef } from '@renderer/api/ai'
 
 // Mock components that will be created later
 const CardEditorHost = defineAsyncComponent(() => import('@renderer/components/cards/CardEditorHost.vue'));
 const CardMarket = defineAsyncComponent(() => import('@renderer/components/cards/CardMarket.vue'));
 const CardExportDialog = defineAsyncComponent(() => import('@renderer/components/cards/CardExportDialog.vue'));


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

function openExportDialog() {
  if (!projectStore.currentProject?.id) {
    ElMessage.warning('请先选择项目')
    return
  }
  if ((cards.value || []).length === 0) {
    ElMessage.warning('当前项目暂无可导出的卡片')
    return
  }
  exportDialogVisible.value = true
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
 // 当某节点的直接子卡片中，任一“类型的数量 > 2”时，为该类型创建一个虚拟分组节点；
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
              __parentCardId: n.id,  // 保存实际父卡片ID
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
const relationGraphRefreshSeq = ref(0)
const activeRightTab = ref('assistant')
const isCreateCardDialogVisible = ref(false)
const exportDialogVisible = ref(false)
const prefetchedContext = ref<any>(null)
const newCardForm = reactive<Partial<CardCreate>>({
  title: '',
  card_type_id: undefined,
  parent_id: '' as any
})

// 卡片多选状态
const selectedCardIds = ref<number[]>([])
const lastSelectedCardId = ref<number | null>(null)

// 空白区域菜单状态
const blankMenuVisible = ref(false)
const blankMenuX = ref(0)
const blankMenuY = ref(0)
const blankMenuRef = ref<HTMLElement | null>(null)

// Search State
const searchQuery = ref('')
const searchResults = ref<CardRead[]>([])
const isSearching = computed(() => searchQuery.value.trim().length > 0)
const searchLoading = ref(false)

const handleSearch = debounce(async (query: string) => {
  if (!query.trim()) {
    searchResults.value = []
    return
  }
  searchLoading.value = true
  try {
    const pid = projectStore.currentProject?.id
    if (pid) {
      searchResults.value = await searchCards(pid, query)
    }
  } catch (e) {
    console.error(e)
  } finally {
    searchLoading.value = false
  }
}, 300)

// Composables
  const { leftSidebarWidth, rightSidebarWidth, startResizing } = useSidebarResizer()
  const isLeftSidebarVisible = ref(true)
  const leftSidebarDisplayWidth = computed(() => (isLeftSidebarVisible.value ? leftSidebarWidth.value : 0))
  
  function toggleLeftSidebar() {
    isLeftSidebarVisible.value = !isLeftSidebarVisible.value
  }
  
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
     // 从类型列表拖拽到空白区域，在根创建新卡片
     newCardForm.title = (cardStore.cardTypes.find(ct => ct.id === Number(typeId))?.name || '新卡片')
     newCardForm.card_type_id = Number(typeId)
     newCardForm.parent_id = '' as any
     handleCreateCard()
     return
   }
   // 从 __free__ 项目跨项目拖拽复制到空白区域
   const freeCardId = e.dataTransfer?.getData('application/x-free-card-id')
   if (freeCardId) {
     await copyCard(Number(freeCardId), { target_project_id: projectStore.currentProject!.id, parent_id: null as any })
     await cardStore.fetchCards(projectStore.currentProject!.id)
     ElMessage.success('已复制自由卡片到根目录')
     return
   }
   // 注意：同项目内的卡片拖拽现在由 el-tree 的原生拖拽处理（handleNodeDrop）
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

// ===== el-tree 原生拖拽功能 =====

// 控制哪些节点可以被拖拽
function handleAllowDrag(draggingNode: any): boolean {
  // 分组节点不允许拖拽
  if (draggingNode.data.__isGroup) {
    return false
  }
  return true
}

// 控制拖拽放置的位置
// type: 'prev' | 'inner' | 'next' 表示放置在目标节点的前/内/后
function handleAllowDrop(draggingNode: any, dropNode: any, type: 'prev' | 'inner' | 'next'): boolean {
  // 分组节点只允许作为"inner"目标（即将卡片放入分组内）
  if (dropNode.data.__isGroup) {
    return type === 'inner'
  }
  
  // 普通卡片节点允许所有放置方式
  return true
}

// 处理拖拽完成
async function handleNodeDrop(
  draggingNode: any,
  dropNode: any,
  dropType: 'before' | 'after' | 'inner',
  ev: DragEvent
) {
  try {
    const draggedCard = draggingNode.data
    const targetCard = dropNode.data
    
    // 如果是拖到分组内，设置 parent_id 为 null（根级）
    if (targetCard.__isGroup && dropType === 'inner') {
      // 计算根级的下一个 display_order
      const rootCards = cards.value.filter(c => c.parent_id === null)
      const maxOrder = rootCards.length > 0 ? Math.max(...rootCards.map(c => c.display_order || 0)) : -1
      
      await cardStore.modifyCard(draggedCard.id, { 
        parent_id: null,
        display_order: maxOrder + 1
      }, { skipHooks: true })
      ElMessage.success(`已将「${draggedCard.title}」移到根级`)
      await cardStore.fetchCards(projectStore.currentProject!.id)
      
      // 记录移动操作（包含层级变化信息）
      assistantStore.recordOperation(projectStore.currentProject!.id, {
        type: 'move',
        cardId: draggedCard.id,
        cardTitle: draggedCard.title,
        cardType: draggedCard.card_type?.name || 'Unknown',
        detail: '从子卡片移到根级'
      })
      
      // 更新项目结构
      updateProjectStructureContext(activeCard.value?.id)
      return
    }
    
    // 如果是拖到卡片内部（成为子卡片）
    if (dropType === 'inner') {
      // 计算目标卡片的子卡片的下一个 display_order
      const children = cards.value.filter(c => c.parent_id === targetCard.id)
      const maxOrder = children.length > 0 ? Math.max(...children.map(c => c.display_order || 0)) : -1
      
      await cardStore.modifyCard(draggedCard.id, { 
        parent_id: targetCard.id,
        display_order: maxOrder + 1
      }, { skipHooks: true })
      ElMessage.success(`已将「${draggedCard.title}」设为「${targetCard.title}」的子卡片`)
      await cardStore.fetchCards(projectStore.currentProject!.id)
      
      // 记录移动操作（包含层级变化信息）
      assistantStore.recordOperation(projectStore.currentProject!.id, {
        type: 'move',
        cardId: draggedCard.id,
        cardTitle: draggedCard.title,
        cardType: draggedCard.card_type?.name || 'Unknown',
        detail: `设为「${targetCard.title}」(${targetCard.card_type?.name || 'Unknown'} #${targetCard.id})的子卡片`
      })
      
      // 更新项目结构
      updateProjectStructureContext(activeCard.value?.id)
      return
    }
    
    // 如果是拖到卡片前/后（同级排序）
    const newParentId = targetCard.parent_id || null
    
    // 获取同级的所有卡片，按 display_order 排序（不包括拖拽的卡片）
    const siblings = cards.value
      .filter(c => (c.parent_id || null) === newParentId && c.id !== draggedCard.id)
      .sort((a, b) => (a.display_order || 0) - (b.display_order || 0))
    
    // 找到目标卡片在同级中的位置
    const targetIndex = siblings.findIndex(c => c.id === targetCard.id)
    
    // 构建新的顺序数组（插入拖拽的卡片）
    let newSiblings = [...siblings]
    if (dropType === 'before') {
      // 插入到目标卡片之前
      newSiblings.splice(targetIndex, 0, draggedCard)
    } else {
      // 插入到目标卡片之后
      newSiblings.splice(targetIndex + 1, 0, draggedCard)
    }
    
    // 批量更新所有受影响卡片的 display_order（使用批量API）
    const updates: Array<{ card_id: number; display_order: number; parent_id?: number | null }> = []
    
    newSiblings.forEach((card, index) => {
      if (card.id === draggedCard.id) {
        // 拖拽的卡片需要同时更新 parent_id 和 display_order
        updates.push({
          card_id: card.id,
          display_order: index,
          parent_id: newParentId
        })
      } else if (card.display_order !== index) {
        // 其他卡片只需要更新 display_order（如果有变化）
        // ⚠️ 重要：必须传递 parent_id，否则后端会错误地将其设置为 null！
        updates.push({
          card_id: card.id,
          display_order: index,
          parent_id: card.parent_id || null  // 保持原有的 parent_id
        })
      }
    })
    
    // 调用批量更新API
    if (updates.length > 0) {
      const { batchReorderCards } = await import('@renderer/api/cards')
      await batchReorderCards({ updates })
    }
    
    ElMessage.success(`已调整「${draggedCard.title}」的位置`)
    await cardStore.fetchCards(projectStore.currentProject!.id)
    
    // 记录移动操作（包含位置和父级信息）
    const targetCardTitle = targetCard?.title || '根目录'
    const positionText = dropType === 'before' ? '之前' : '之后'
    let moveDetail = `移动到「${targetCardTitle}」${positionText}`
    
    // 如果改变了父级，特别标注
    if (draggedCard.parent_id !== newParentId) {
      // 优化：创建 Map 避免多次 find（仅在父级变化时）
      const cardMap = new Map(cards.value.map(c => [(c as any).id, c.title]))
      const oldParentName = draggedCard.parent_id 
        ? cardMap.get(draggedCard.parent_id) || '未知' 
        : '根目录'
      const newParentName = newParentId 
        ? cardMap.get(newParentId) || '未知' 
        : '根目录'
      moveDetail += ` (从「${oldParentName}」移到「${newParentName}」)`
    }
    
    assistantStore.recordOperation(projectStore.currentProject!.id, {
      type: 'move',
      cardId: draggedCard.id,
      cardTitle: draggedCard.title,
      cardType: draggedCard.card_type?.name || 'Unknown',
      detail: moveDetail
    })
    
    // 立即更新项目结构，让灵感助手感知层级变化
    updateProjectStructureContext(activeCard.value?.id)
    
  } catch (err: any) {
    console.error('拖拽失败:', err)
    ElMessage.error(err?.message || '拖拽失败')
    // 刷新以恢复状态
    await cardStore.fetchCards(projectStore.currentProject!.id)
    // 即使失败也更新结构
    updateProjectStructureContext(activeCard.value?.id)
  }
}

// --- 拖拽：从外部（类型列表、自由卡片）到卡片树 ---
// 注意：el-tree 内部的卡片拖拽由 handleNodeDrop 处理，这里只处理外部拖入

function getDraggedTypeId(e: DragEvent): number | null {
 try {
   const raw = e.dataTransfer?.getData('application/x-card-type-id') || ''
   const n = Number(raw)
   return Number.isFinite(n) && n > 0 ? n : null
 } catch { return null }
}

async function onExternalDropToNode(e: DragEvent, nodeData: any) {
 // 只处理从类型列表或跨项目的拖拽，不处理树内部的卡片拖拽
 const typeId = getDraggedTypeId(e)
 if (typeId) {
   // 从类型列表拖拽创建新卡片
   if (nodeData?.__isGroup) return
   const newCard = await cardStore.addCard({ title: '新建卡片', card_type_id: typeId, parent_id: nodeData?.id } as any)
   
   //  记录创建操作
   if (newCard && projectStore.currentProject?.id) {
     const cardType = cardStore.cardTypes.find(ct => ct.id === typeId)
     assistantStore.recordOperation(projectStore.currentProject.id, {
       type: 'create',
       cardId: (newCard as any).id,
       cardTitle: newCard.title,
       cardType: cardType?.name || 'Unknown'
     })
   }
   
   return
 }
 
 try {
   // 处理从 __free__ 跨项目拖拽复制
   const freeCardId = e.dataTransfer?.getData('application/x-free-card-id')
   if (freeCardId) {
     if (nodeData?.__isGroup) return
     await copyCard(Number(freeCardId), { target_project_id: projectStore.currentProject!.id, parent_id: Number(nodeData?.id) })
     await cardStore.fetchCards(projectStore.currentProject!.id)
     ElMessage.success('已复制自由卡片到该节点下')
     return
   }
 } catch (err) {
   console.error('外部拖拽失败:', err)
 }
}

 // --- Methods ---

// 点击行为对"分组节点"不做打开编辑，仅用于展开/折叠。对实际卡片才触发编辑。
function handleNodeClick(data: any) {
  if (data.__isGroup) return
  
  // 确保点击的卡片被选中（用于UI高亮），同时覆盖 handleCardClick 中的清空操作
  selectedCardIds.value = [data.id]
  lastSelectedCardId.value = data.id

  // 章节正文现在也在中栏编辑器中打开
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
      assistantStore.addAutoRef({
        refType: 'card',
        projectId: pid,
        projectName: pname,
        cardId: data.id,
        cardTitle: title,
        content,
      })
    }
  } catch {}
}

// 卡片点击处理（支持多选）
function handleCardClick(event: MouseEvent, data: any) {
  // 分组节点不支持多选
  if (data.__isGroup) {
    handleNodeClick(data)
    return
  }
  
  const cardId = data.id
  
  // Ctrl 键：跳跃式多选
  if (event.ctrlKey || event.metaKey) {
    const index = selectedCardIds.value.indexOf(cardId)
    if (index > -1) {
      // 取消选中
      selectedCardIds.value.splice(index, 1)
    } else {
      // 添加选中
      selectedCardIds.value.push(cardId)
    }
    lastSelectedCardId.value = cardId
    event.stopPropagation()
    return
  }
  
  // Shift 键：连续多选
  if (event.shiftKey && lastSelectedCardId.value !== null) {
    // 获取所有可见的卡片ID（扁平化树结构）
    const flatCards: number[] = []
    function flattenTree(nodes: any[]) {
      for (const node of nodes) {
        if (!node.__isGroup && node.id) {
          flatCards.push(node.id)
        }
        if (node.children && node.children.length > 0) {
          flattenTree(node.children)
        }
      }
    }
    flattenTree(groupedTree.value)
    
    // 找到起始和结束位置
    const startIndex = flatCards.indexOf(lastSelectedCardId.value)
    const endIndex = flatCards.indexOf(cardId)
    
    if (startIndex !== -1 && endIndex !== -1) {
      const minIndex = Math.min(startIndex, endIndex)
      const maxIndex = Math.max(startIndex, endIndex)
      
      // 选中范围内的所有卡片
      selectedCardIds.value = flatCards.slice(minIndex, maxIndex + 1)
    }
    
    event.stopPropagation()
    return
  }
  
  // 普通点击：交由 handleNodeClick 处理选中和激活
  handleNodeClick(data)
}

// 判断卡片是否被选中
function isCardSelected(cardId: number): boolean {
  return selectedCardIds.value.includes(cardId)
}

// 批量删除卡片
async function batchDeleteCards() {
  if (selectedCardIds.value.length === 0) {
    ElMessage.warning('请先选择要删除的卡片')
    return
  }
  
  try {
    await ElMessageBox.confirm(
      `确认删除选中的 ${selectedCardIds.value.length} 个卡片？此操作不可恢复`,
      '批量删除确认',
      { type: 'warning' }
    )
    
    // 记录删除的卡片信息
    const deletedCards = selectedCardIds.value.map(id => {
      const card = cards.value.find(c => (c as any).id === id)
      return {
        id,
        title: card?.title || '未知',
        cardType: (card as any)?.card_type?.name || 'Unknown'
      }
    })
    
    // 如果当前激活的卡片在删除列表中，先清空激活状态
    if (activeCard.value && selectedCardIds.value.includes((activeCard.value as any).id)) {
      cardStore.setActiveCard(null as any)
    }
    
    // 优化：过滤掉会被级联删除的子卡片
    // 只删除顶层卡片（即不是其他选中卡片的子孙的卡片）
    const selectedSet = new Set(selectedCardIds.value)
    const cardsToDelete: number[] = []
    
    // 检查一个卡片是否是另一个选中卡片的子孙
    function isDescendantOfSelected(cardId: number): boolean {
      const card = cards.value.find(c => (c as any).id === cardId)
      if (!card) return false
      
      let parentId = (card as any).parent_id
      while (parentId) {
        if (selectedSet.has(parentId)) {
          return true  // 是某个选中卡片的子孙
        }
        const parent = cards.value.find(c => (c as any).id === parentId)
        if (!parent) break
        parentId = (parent as any).parent_id
      }
      return false
    }
    
    // 只保留顶层卡片（不是其他选中卡片的子孙）
    for (const cardId of selectedCardIds.value) {
      if (!isDescendantOfSelected(cardId)) {
        cardsToDelete.push(cardId)
      }
    }
    
    // 批量删除（只删除顶层卡片，子卡片会被后端级联删除）
    let successCount = 0
    for (const cardId of cardsToDelete) {
      try {
        await cardStore.removeCard(cardId)
        successCount++
      } catch (error: any) {
        console.error(`删除卡片 ${cardId} 失败:`, error)
        ElMessage.error(`删除卡片失败: ${error.message || '未知错误'}`)
      }
    }
    
    // 记录删除操作（记录所有选中的卡片，包括被级联删除的）
    if (projectStore.currentProject?.id) {
      for (const card of deletedCards) {
        assistantStore.recordOperation(projectStore.currentProject.id, {
          type: 'delete',
          cardId: card.id,
          cardTitle: card.title,
          cardType: card.cardType
        })
      }
    }
    
    // 清空选中状态
    selectedCardIds.value = []
    lastSelectedCardId.value = null
    
    ElMessage.success(`已删除 ${selectedCardIds.value.length || deletedCards.length} 个卡片`)
  } catch (e) {
    // 用户取消
  }
}

// 兜底：当 activeCard 改变时也自动注入一次
watch(activeCard, (c) => {
 try {
   if (!c) return
   const pid = projectStore.currentProject?.id as number
   const pname = projectStore.currentProject?.name || ''
  assistantStore.addAutoRef({
    refType: 'card',
    projectId: pid,
    projectName: pname,
    cardId: (c as any).id,
    cardTitle: (c as any).title || '',
    content: (c as any).content || {},
  })
   
   //  更新卡片上下文（用于灵感助手工具调用）
   assistantStore.updateActiveCard(c as any, pid)
   
   //  更新项目结构（当前卡片变化时）
   updateProjectStructureContext((c as any)?.id)
 } catch (err) {
   console.error('🔄 [Editor] 更新卡片上下文失败:', err)
 }
})

//  监听项目切换，初始化结构和操作历史
watch(() => projectStore.currentProject, (newProject) => {
  if (!newProject?.id) return
  
  // 切换项目时重置搜索
  searchQuery.value = ''
  searchResults.value = []

  try {
    // 加载操作历史
    assistantStore.loadOperations(newProject.id)
    
    // 更新卡片类型列表
    assistantStore.updateProjectCardTypes(cardStore.cardTypes.map(ct => ct.name))
    
    // 构建项目结构
    updateProjectStructureContext(activeCard.value?.id)
  } catch (err) {
    console.error('📦 [Editor] 初始化助手上下文失败:', err)
  }
}, { immediate: true })

//  监听卡片数量变化（新增/删除），自动更新项目结构
// 优化：只监听数量变化，层级变化由拖拽操作手动触发
watch(() => cards.value.length, () => {
  try {
    updateProjectStructureContext(activeCard.value?.id)
  } catch (err) {
    console.error('🔄 [Editor] 更新项目结构失败:', err)
  }
})

//  统一更新项目结构的函数
function updateProjectStructureContext(currentCardId?: number) {
  const project = projectStore.currentProject
  if (!project?.id) return
  
  assistantStore.updateProjectStructure(
    project.id,
    project.name,
    cards.value,
    cardStore.cardTypes,
    currentCardId
  )
}

function onNodeExpand(_: any, node: any) {
  editorStore.addExpandedKey(String(node.key))
}

function onNodeCollapse(_: any, node: any) {
  // 递归移除该节点及其所有子节点的展开状态
  // 这样可以防止刷新数据时，一下子节点触发父节点自动展开
  const removeRecursively = (n: any) => {
    if (n.key) {
      editorStore.removeExpandedKey(String(n.key))
    }
    if (n.childNodes && n.childNodes.length > 0) {
      n.childNodes.forEach((child: any) => removeRecursively(child))
    }
  }
  removeRecursively(node)
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
  const newCard = await cardStore.addCard(payload as CardCreate);
  
  //  记录创建操作
  if (newCard && projectStore.currentProject?.id) {
    const cardType = cardStore.cardTypes.find(ct => ct.id === newCardForm.card_type_id)
    assistantStore.recordOperation(projectStore.currentProject.id, {
      type: 'create',
      cardId: (newCard as any).id,
      cardTitle: newCard.title,
      cardType: cardType?.name || 'Unknown'
    })
  }
  
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
    case '文件夹':
      return Folder
    default:
      return Document // 通用默认图标
  }
}

// 右键菜单命令处理（新建子卡片、删除卡片）
function handleContextCommand(command: string, data: any) {
  if (command === 'create-child') {
    openCreateChild(data.id)
  } else if (command === 'create-child-in-group') {
    // 分组节点：使用实际父卡片ID，并预设卡片类型
    openCreateChildInGroup(data.__parentCardId, data.__groupType)
  } else if (command === 'delete') {
    deleteNode(data.id, data.title)
  } else if (command === 'batch-delete') {
    batchDeleteCards()
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
      assistantStore.addInjectedRefDirect({
        refType: 'card',
        projectId: pid,
        projectName: pname,
        cardId: data.id,
        cardTitle: title,
        content,
      }, 'manual')
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

// 打开"新建卡片"对话框并预填父ID
function openCreateChild(parentId: number) {
  newCardForm.title = ''
  newCardForm.card_type_id = undefined
  newCardForm.parent_id = parentId as any
  isCreateCardDialogVisible.value = true
}

// 打开"新建卡片"对话框（分组节点专用）：预填父ID和卡片类型
function openCreateChildInGroup(parentId: number, groupType: string) {
  newCardForm.title = ''
  newCardForm.parent_id = parentId as any
  
  // 根据分组类型名称查找对应的卡片类型ID
  const cardType = cardStore.cardTypes.find(ct => ct.name === groupType)
  newCardForm.card_type_id = cardType?.id
  
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
    
    //  删除前记录卡片信息
    const card = cards.value.find(c => (c as any).id === cardId)
    const cardType = card ? ((card as any).card_type?.name || 'Unknown') : 'Unknown'
    
    // 如果删除的是当前激活的卡片，先清空激活状态
    if (activeCard.value && (activeCard.value as any).id === cardId) {
      cardStore.setActiveCard(null as any)
    }
    
    try {
      await cardStore.removeCard(cardId)
      ElMessage.success('卡片已删除')
      
      //  记录删除操作
      if (projectStore.currentProject?.id) {
        assistantStore.recordOperation(projectStore.currentProject.id, {
          type: 'delete',
          cardId,
          cardTitle: title,
          cardType
        })
      }
    } catch (error: any) {
      console.error('删除卡片失败:', error)
      ElMessage.error('删除卡片失败')
    }
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
    // 默认仅更新外壳 card.title
    const card = (cards.value || []).find((c: any) => c.id === cardId) as any
    const payload: any = { title: newTitle }

    // 仅对章节大纲 / 章节正文做「标题字段与卡片名」的绑定优化
    const typeName = card?.card_type?.name || ''
    if ((typeName === '章节大纲' || typeName === '章节正文') && card?.content) {
      const content: any = { ...(card.content as any) }
      content.title = newTitle
      payload.content = content
    }
    await cardStore.modifyCard(cardId, payload)
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

// 判断当前是否为章节正文卡片
const isChapterContent = computed(() => {
  return activeCard.value?.card_type?.name === '章节正文'
})

const showRightSidebarTabs = computed(() => {
  return Boolean(activeCard.value)
})

const reviewTargetCardIdForSidebar = computed<number | null>(() => {
  const card = activeCard.value as any
  if (!card) return null
  if (card?.card_type?.name === '内容审核卡片') {
    const target = Number(card?.content?.review_target_card_id || 0)
    return Number.isFinite(target) && target > 0 ? target : null
  }
  return Number(card.id || 0) || null
})

const rightSidebarTabNames = computed(() => {
  if (!showRightSidebarTabs.value) return [] as string[]
  if (isChapterContent.value) return ['assistant', 'context', 'extract', 'outline', 'review-history']
  return ['assistant', 'review-history']
})

// 章节信息提取
const chapterVolumeNumber = computed(() => {
  if (!isChapterContent.value) return null
  const content: any = activeCard.value?.content || {}
  return content.volume_number ?? null
})

const chapterChapterNumber = computed(() => {
  if (!isChapterContent.value) return null
  const content: any = activeCard.value?.content || {}
  return content.chapter_number ?? null
})

const chapterParticipants = computed(() => {
  if (!isChapterContent.value) return []
  const content: any = activeCard.value?.content || {}
  const list = content.entity_list || []
  if (Array.isArray(list)) {
    return list.map((x: any) => typeof x === 'string' ? x : (x?.name || '')).filter(Boolean).slice(0, 6)
  }
  return []
})

// 自动装配章节上下文（首次进入章节正文时）
watch(isChapterContent, async (val) => {
  if (val && activeCard.value) {
    await assembleChapterContext()
  }
}, { immediate: true })

watch(rightSidebarTabNames, (tabNames) => {
  if (!tabNames.includes(activeRightTab.value)) {
    activeRightTab.value = 'assistant'
  }
}, { immediate: true })

// 当卡片仓库内容发生变化时，若当前仍在章节正文卡片上，则重新装配上下文
watch(cards, async () => {
  if (isChapterContent.value && activeCard.value) {
    await assembleChapterContext()
  }
})

async function assembleChapterContext() {
  if (!isChapterContent.value || !projectStore.currentProject?.id) return
  
  try {
    const { assembleContext } = await import('@renderer/api/ai')
    const res = await assembleContext({
      project_id: projectStore.currentProject.id,
      volume_number: chapterVolumeNumber.value ?? undefined,
      chapter_number: chapterChapterNumber.value ?? undefined,
      participants: chapterParticipants.value,
      current_draft_tail: ''
    })
    prefetchedContext.value = res
  } catch (e) {
    console.error('Failed to assemble chapter context:', e)
  }
}

// 当右侧“参与实体”面板中手动增删参与者时，将变更写回当前章节卡片的内容
async function handleContextParticipantsUpdate(names: string[]) {
  try {
    if (!isChapterContent.value || !activeCard.value) return
    const card = activeCard.value as any
    const content: any = { ...(card.content || {}) }
    // 仅以名称列表作为实体列表的来源（对象形态后续仍可由分析流程补全）
    const normalized = (names || [])
      .map(n => (typeof n === 'string' ? n.trim() : String(n || '')).trim())
      .filter(Boolean)
    content.entity_list = normalized
    await cardStore.modifyCard(card.id, { content } as any)
    // modifyCard 成功后，cards watcher 会触发 assembleChapterContext 使用新的参与者
  } catch (e) {
    console.error('Failed to update participants on card:', e)
  }
}

function handleContextAssembledUpdate(ctx: any) {
  prefetchedContext.value = ctx || null
}


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

watch(activeTab, (tab) => {
  if (tab === 'relation-graph') {
    relationGraphRefreshSeq.value += 1
  }
})

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

function onAssistantAddRef(e: CustomEvent) {
  try {
    const payload = (e as any)?.detail || {}
    const ref = (payload.ref || payload) as AssistantRef
    assistantStore.addInjectedRefDirect(ref, (ref as any)?.source || 'manual')
    activeRightTab.value = 'assistant'
  } catch {}
}

function onAssistantAddExcerptRef(e: CustomEvent) {
  try {
    const payload = (e as any)?.detail || {}
    const ref = (payload.ref || payload) as ChapterExcerptRef
    assistantStore.addChapterExcerptRef(ref, (ref as any)?.source || 'manual')
    activeRightTab.value = 'assistant'
  } catch {}
}

function onAssistantAddReviewRef(e: CustomEvent) {
  try {
    const payload = (e as any)?.detail || {}
    const ref = (payload.ref || payload) as ReviewResultRef
    assistantStore.addReviewResultRef(ref, (ref as any)?.source || 'manual')
    activeRightTab.value = 'assistant'
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

function onJumpToCardEvent(e: CustomEvent) {
  const detail = (e as any)?.detail || {}
  const cardId = Number(detail.cardId || 0)
  if (!cardId) return
  void handleJumpToCard({
    projectId: Number(detail.projectId || projectStore.currentProject?.id || 0),
    cardId,
  })
}

// --- Lifecycle ---

onMounted(async () => {
  // Fetch initial data for the card system (like types and models)
  // Cards will be fetched automatically by the watcher in the card store
  await cardStore.fetchInitialData()
  // 进入编辑页时也刷新一次可用模型（处理应用在其他页新增模型的场景）
  await cardStore.fetchAvailableModels()
  
  // 更新项目卡片类型列表（用于灵感助手工具调用）
  try {
    const types = cardStore.cardTypes.map(t => t.name)
    assistantStore.updateProjectCardTypes(types)
  } catch {}
  
  window.addEventListener('nf:navigate', onNavigate as any)
  window.addEventListener('nf:assistant-finalize', onAssistantFinalize as any)
  window.addEventListener('nf:switch-right-tab', onSwitchRightTab as any)
  window.addEventListener('nf:assistant-add-ref', onAssistantAddRef as any)
  window.addEventListener('nf:assistant-add-excerpt-ref', onAssistantAddExcerptRef as any)
  window.addEventListener('nf:assistant-add-review-ref', onAssistantAddReviewRef as any)
  window.addEventListener('nf:jump-to-card', onJumpToCardEvent as any)
  await refreshAssistantContext()
})

 onBeforeUnmount(() => {
   window.removeEventListener('nf:navigate', onNavigate as any)
   window.removeEventListener('nf:assistant-finalize', onAssistantFinalize as any)
   window.removeEventListener('nf:switch-right-tab', onSwitchRightTab as any)
   window.removeEventListener('nf:assistant-add-ref', onAssistantAddRef as any)
   window.removeEventListener('nf:assistant-add-excerpt-ref', onAssistantAddExcerptRef as any)
   window.removeEventListener('nf:assistant-add-review-ref', onAssistantAddReviewRef as any)
   window.removeEventListener('nf:jump-to-card', onJumpToCardEvent as any)
  })

 function onNavigate(e: CustomEvent) {
   if ((e as any).detail?.to === 'market') {
     activeTab.value = 'market'
   }
 }

function onSwitchRightTab(e: CustomEvent) {
  const tab = (e as any)?.detail?.tab
  if (tab && rightSidebarTabNames.value.includes(tab)) {
    activeRightTab.value = tab
  }
}

 // 点击页面任意处隐藏空白菜单
 document.addEventListener('click', () => (blankMenuVisible.value = false))

 const treeRef = ref<any>(null)

 watch(groupedTree, async () => {
   // Wait for the tree to re-render with new data
   await nextTick()
   try { 
     if (expandedKeys.value.length > 0) {
       // Using Element Plus Tree store API to set expanded keys
       // This is more reliable than manipulating nodes directly
       treeRef.value?.store?.setDefaultExpandedKeys(expandedKeys.value)
     }
   } catch (e) {
     console.error('Failed to restore expanded state:', e)
   }
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
  background-color: var(--el-fill-color-lighter); /* 适配暗黑模式 */
}

.sidebar {
  display: flex;
  flex-direction: column;
  background-color: var(--el-fill-color-lighter); /* 适配暗黑模式 */
  transition: width 0.2s;
  flex-shrink: 0;
  overflow: hidden;
  border-right: none; /* 移除边框 */
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
  padding: 16px 8px; /* 留出边距 */
  display: flex;
  flex-direction: column;
  background-color: transparent; /* 透明背景 */
}

.main-tabs {
  flex-grow: 1;
  display: flex;
  flex-direction: column;
  background-color: var(--el-bg-color); /* 适配暗黑模式 */
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08); /* 轻微阴影 */
  border-radius: 8px; /* 圆角 */
  overflow: hidden; /* 确保内容不溢出圆角 */
  border: none; /* 移除默认边框 */
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
  border-radius: 4px;
  transition: background-color 0.2s;
}
.custom-tree-node.full-row .label {
  flex: 1;
}
.custom-tree-node.full-row.selected {
  background-color: var(--el-color-primary-light-9);
  border: 1px solid var(--el-color-primary-light-7);
}
.custom-tree-node.full-row.selected .label {
  color: var(--el-color-primary);
  font-weight: 500;
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
.assistant-sidebar { 
  border-left: none; 
  background: transparent; 
  flex-shrink: 0; 
  padding: 16px 8px 16px 0; /* 右侧留白 */
}
.right-resizer { cursor: col-resize; width: 5px; background: transparent; }
.right-resizer:hover { background: var(--el-color-primary-light-7); }
.left-sidebar-toggle {
  position: absolute;
  left: 12px;
  bottom: 12px;
  z-index: 30;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
}
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

/* 右栏Tab样式 */
.right-tabs {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--el-bg-color);
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  overflow: hidden;
}
.right-tabs :deep(.el-tabs__header) {
  margin: 0;
  border-bottom: 1px solid var(--el-border-color-light);
  padding: 12px 12px 0 12px;
  background: var(--el-fill-color-lighter);
}
.right-tabs :deep(.el-tabs__nav-wrap) {
  padding: 0;
}
.right-tabs :deep(.el-tabs__item) {
  font-size: 13px;
  font-weight: 500;
  padding: 0 16px;
  height: 36px;
  line-height: 36px;
}
.right-tabs :deep(.el-tabs__item.is-active) {
  color: var(--el-color-primary);
}
.right-tabs :deep(.el-tabs__content) {
  flex: 1;
  overflow: hidden;
  padding: 0;
}
.right-tabs :deep(.el-tab-pane) {
  height: 100%;
  overflow-y: auto;
}

.search-results-list {
  flex-grow: 1;
  overflow-y: auto;
  padding: 0 8px;
}
.search-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  cursor: pointer;
  border-radius: 4px;
  color: var(--el-text-color-primary);
  font-size: 14px;
  transition: background-color 0.2s;
}
.search-item:hover {
  background-color: var(--el-fill-color-light);
}
.search-item-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
