<template>
  <div class="editor-layout">
    <!-- 左侧卡片导航树 -->
    <el-aside class="sidebar card-navigation-sidebar" :style="{ width: leftSidebarWidth + 'px' }">
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
                <el-dropdown-item v-if="!data.__isGroup" command="create-child">新建子卡片</el-dropdown-item>
                <el-dropdown-item v-if="!data.__isGroup" command="delete" divided>删除卡片</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </template>
      </el-tree>
      <el-empty v-else description="暂无卡片" :image-size="80"></el-empty>
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
const { cardTree, activeCard } = storeToRefs(cardStore)
const editorStore = useEditorStore()
const { expandedKeys } = storeToRefs(editorStore)

// --- 前端自动分组器 ---
// 设计：当某节点的直接子卡片存在“某类型的数量 > 1”时，为该类型创建一个虚拟分组节点（只对数量>1的类型建组）
// 例如：2 张「角色卡」+ 1 张「场景卡」=> 仅生成一个「角色卡」分组；「场景卡」保持原状
// 该结构完全在前端进行，不影响后端数据
interface TreeNode { id: number | string; title: string; children?: TreeNode[]; card_type?: { name: string }; __isGroup?: boolean; __groupType?: string }

function buildGroupedNodes(nodes: any[]): any[] {
  return nodes.map(n => {
    const node: TreeNode = { ...n }
    if (Array.isArray(n.children) && n.children.length > 0) {
      // 统计子节点类型数量
      const byType: Record<string, any[]> = {}
      n.children.forEach((c: any) => {
        const typeName = c.card_type?.name || '未知类型'
        if (!byType[typeName]) byType[typeName] = []
        byType[typeName].push(c)
      })
      // 是否有多个类型，且某类型数量>1
      const types = Object.keys(byType)
      const hasMultipleTypes = types.length > 1
      if (hasMultipleTypes) {
        const grouped: any[] = []
        types.forEach(t => {
          const list = byType[t]
          if (list.length > 1) {
            // 创建虚拟分组节点（id 使用字符串避免冲突）
            grouped.push({
              id: `group:${n.id}:${t}`,
              title: `${t}`,
              __isGroup: true,
              __groupType: t,
              children: list.map(x => ({ ...x }))
            })
          } else {
            grouped.push(list[0])
          }
        })
        node.children = grouped.map(x => ({ ...x }))
      } else {
        // 只有一种类型，保持原样
        node.children = n.children.map((c: any) => ({ ...c }))
      }
      // 递归对子树继续处理
      node.children = buildGroupedNodes(node.children as any)
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
  parent_id: undefined
})

// Composables
const { leftSidebarWidth, startResizing } = useSidebarResizer()

// --- Methods ---

// 点击行为对“分组节点”不做打开编辑，仅用于展开/折叠。对实际卡片才触发编辑。
function handleNodeClick(data: any) {
  if (data.__isGroup) return
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
  await cardStore.addCard(newCardForm as CardCreate);
  isCreateCardDialogVisible.value = false;
  // Reset form
  Object.assign(newCardForm, { title: '', card_type_id: undefined, parent_id: undefined });
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
  }
}

// 打开“新建卡片”对话框并预填父ID
function openCreateChild(parentId: number) {
  newCardForm.title = ''
  newCardForm.card_type_id = undefined
  newCardForm.parent_id = parentId
  isCreateCardDialogVisible.value = true
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

// --- Lifecycle ---

onMounted(async () => {
  // Fetch initial data for the card system (like types and models)
  // Cards will be fetched automatically by the watcher in the card store
  await cardStore.fetchInitialData()
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
</script>

<style scoped>
/* 让右键触发区域充满整行 */
.full-row-dropdown { display: block; width: 100%; }

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