<template>
  <div class="editor-layout">
    <!-- 左侧卡片导航树 -->
    <el-aside class="sidebar card-navigation-sidebar" :style="{ width: leftSidebarWidth + 'px' }" @contextmenu.prevent="onSidebarContextMenu">
      <div class="sidebar-header">
        <h3 class="sidebar-title">创作卡片</h3>
        <el-button type="primary" size="small" :icon="Plus" @click="isCreateCardDialogVisible = true">
          新建卡片
        </el-button>
      </div>
      <el-tree
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
            <div class="custom-tree-node full-row">
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
        <!-- 将“卡片集市”改为“卡片库”，更贴近素材库/资源库的含义 -->
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
</template>

<script setup lang="ts">
import { ref, onMounted, reactive, defineAsyncComponent, onBeforeUnmount, computed } from 'vue'
import { storeToRefs } from 'pinia'
import { Plus } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
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
import { useCardStore } from '@renderer/stores/useCardStore'
import { ElMessage } from 'element-plus'
import { useEditorStore } from '@renderer/stores/useEditorStore'
import { useProjectStore } from '@renderer/stores/useProjectStore'
 
 // Mock components that will be created later
 const CardEditorHost = defineAsyncComponent(() => import('@renderer/components/cards/CardEditorHost.vue'));
 const CardMarket = defineAsyncComponent(() => import('@renderer/components/cards/CardMarket.vue'));


 type Project = components['schemas']['ProjectRead']
 type CardRead = components['schemas']['CardRead']
 type CardCreate = components['schemas']['CardCreate']

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
 const { leftSidebarWidth, startResizing } = useSidebarResizer()

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
   activeTab.value = 'editor'
 }

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
   }
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

 // --- Lifecycle ---

 onMounted(async () => {
   // Fetch initial data for the card system (like types and models)
   // Cards will be fetched automatically by the watcher in the card store
   await cardStore.fetchInitialData()
   // 保险：进入编辑页时也刷新一次可用模型（处理应用在其他页新增模型的场景）
   await cardStore.fetchAvailableModels()
   window.addEventListener('nf:navigate', onNavigate as any)
 })

 onBeforeUnmount(() => {
   window.removeEventListener('nf:navigate', onNavigate as any)
 })

 function onNavigate(e: CustomEvent) {
   if ((e as any).detail?.to === 'market') {
     activeTab.value = 'market'
   }
 }

 // 点击页面任意处隐藏空白菜单
 document.addEventListener('click', () => (blankMenuVisible.value = false))
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
  padding: 10px;
}

.sidebar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
  padding: 0 5px;
}

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
  padding: 4px 6px;
}
.custom-tree-node.full-row .label {
  flex: 1;
}
/* 分组节点沿用通用样式，图标由类型映射决定；自适应无需额外样式 */
</style>