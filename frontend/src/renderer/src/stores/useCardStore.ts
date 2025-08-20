import { defineStore, storeToRefs } from 'pinia'
import { ref, computed, watch } from 'vue'
import {
  getCardTypes,
  getCardsForProject,
  createCard,
  updateCard,
  deleteCard,
  getContentModels,
  type CardRead,
  type CardTypeRead,
  type CardCreate,
  type CardUpdate
} from '@renderer/api/cards'
import { useProjectStore } from './useProjectStore'
import { ElMessage } from 'element-plus'

// Helper function to build a tree from a flat list of cards
// 为了避免直接在 CardRead 上添加 children 属性，这里定义本地扩展类型
type CardNode = CardRead & { children: CardNode[] }
const buildCardTree = (cards: CardRead[]): CardNode[] => {
  const cardMap = new Map<number, CardNode>()
  // 将后端返回的扁平列表转换为节点列表，并附加 children 数组
  const nodes: CardNode[] = cards.map((c) => ({ ...(c as CardRead), children: [] as CardNode[] }))
  nodes.forEach((node) => {
    cardMap.set(node.id, node)
  })

  const tree: CardNode[] = []
  nodes.forEach((node) => {
    if (node.parent_id && cardMap.has(node.parent_id)) {
      cardMap.get(node.parent_id)!.children.push(node)
    } else {
      tree.push(node)
    }
  })

  // 按 display_order 对每一层的节点排序
  const sortNodes = (nodes: CardNode[]) => {
    nodes.sort((a, b) => a.display_order - b.display_order)
    nodes.forEach((n) => sortNodes(n.children))
  }
  sortNodes(tree)

  return tree
}


export const useCardStore = defineStore('card', () => {
  const projectStore = useProjectStore()
  const { currentProject } = storeToRefs(projectStore)

  // --- State ---
  const cards = ref<CardRead[]>([])
  const cardTypes = ref<CardTypeRead[]>([])
  const availableModels = ref<string[]>([])
  const activeCardId = ref<number | null>(null)
  const isLoading = ref(false)

  // --- Getters ---
  const cardTree = computed(() => buildCardTree(cards.value) as unknown as CardRead[])
  const activeCard = computed(() => {
    if (activeCardId.value === null) return null
    return cards.value.find((c) => c.id === activeCardId.value) || null
  })

  // --- Watchers ---
  watch(currentProject, (newProject) => {
    if (newProject?.id) {
      fetchCards(newProject.id);
    } else {
      // If there's no project, clear the cards
      cards.value = [];
    }
  }, { immediate: true });

  // --- 内部工具：根据卡片类型名称拿到ID ---
  function getCardTypeIdByName(name: string): number | null {
    const ct = cardTypes.value.find(t => t.name === name)
    return ct ? ct.id : null
  }

  // --- 内部工具：正则解析“第N卷”的标题 ---
  function parseVolumeIndexFromTitle(title: string): number | null {
    const m = title.match(/^第(\d+)卷$/)
    if (!m) return null
    return parseInt(m[1], 10)
  }

  // --- 内部：保存后钩子 ---
  async function runAfterSaveHooks(updatedCard: CardRead) {
    try {
      if (!currentProject.value?.id) return
      // 交给统一 hooks 分发器
      const { cardHooks } = await import('@renderer/services/cardHooks')
      await cardHooks.runAfterSave(updatedCard, {
        getCardTypeIdByName,
        cards,
        currentProjectId: currentProject.value?.id,
        addCard,
        modifyCard,
      })
    } catch (err) {
      console.error('[CardStore] 执行保存后钩子失败：', err)
    }
  }

  // --- Actions ---

  async function fetchInitialData() {
    await Promise.all([
        fetchCardTypes(),
        fetchAvailableModels()
    ]);
  }

  // Card Actions
  async function fetchCards(projectId: number) {
    if (!projectId) {
        cards.value = []
        return
    }
    isLoading.value = true
    try {
      const fetchedCards = await getCardsForProject(projectId)
      console.log(`[CardStore] Fetched ${fetchedCards.length} cards for project ${projectId}:`, fetchedCards);
      cards.value = fetchedCards
    } catch (error) {
      ElMessage.error('Failed to fetch cards.')
      console.error(error)
    } finally {
      isLoading.value = false
    }
  }

  async function addCard(cardData: CardCreate) {
    if (!currentProject.value?.id) return
    try {
      const newCard = await createCard(currentProject.value.id, cardData)
      // 若新建的是特定类型，自动设置默认 AI 参数卡 ID
      try {
        const typeName = (newCard as any)?.card_type?.name
        const defaultParamMap: Record<string, string> = {
          '章节正文': 'card-009',
          '阶段大纲': 'card-007',
          '写作指南': 'card-010',
        }
        const paramId = defaultParamMap[typeName as string]
        if (paramId) {
          await updateCard(newCard.id, { selected_ai_param_card_id: paramId } as any)
        }
      } catch (e) {
        console.warn('[CardStore] 自动设置参数卡失败（可忽略）：', e)
      }
      // 为保证树与排序的正确性，这里简单起见直接刷新
      await fetchCards(currentProject.value.id)
      ElMessage.success(`Card "${newCard.title}" created.`)
    } catch (error) {
      ElMessage.error('Failed to create card.')
      console.error(error)
    }
  }

  // 增加可选参数：skipHooks 用于内部更新时跳过“保存后钩子”
  async function modifyCard(cardId: number, cardData: { content: Record<string, any> | null } | CardUpdate, options?: { skipHooks?: boolean }) {
    try {
      const updatedCard = await updateCard(cardId, cardData as CardUpdate)
      // 若层级或顺序变动，刷新列表
      if ('parent_id' in cardData || 'display_order' in cardData) {
        if (currentProject.value?.id) await fetchCards(currentProject.value.id)
      } else {
        const index = cards.value.findIndex((c) => c.id === cardId)
        if (index !== -1) {
          const existingCard = cards.value[index]
          // 注意：避免在部分更新时将内容误置为 undefined
          // 后端通常返回完整的 updatedCard；若未返回 content，则保留本地 existingCard.content
          const newContent = (cardData as any).content !== undefined ? (cardData as any).content : existingCard.content
          cards.value[index] = { ...existingCard, ...updatedCard, content: newContent }
        }
      }
      ElMessage.success(`Card "${updatedCard.title}" updated.`)

      // 触发通用保存后钩子（除非被请求显式跳过）
      if (!options?.skipHooks) {
        const card = cards.value.find(c => c.id === cardId) || updatedCard
        await runAfterSaveHooks(card as CardRead)
      }
    } catch (error) {
      ElMessage.error('Failed to update card.')
      console.error(error)
    }
  }

  async function removeCard(cardId: number) {
    try {
      await deleteCard(cardId)
      // 后端已做递归删除，这里仅刷新
      if (currentProject.value?.id) await fetchCards(currentProject.value.id)
      ElMessage.success('Card deleted successfully.')
    } catch (error) {
      ElMessage.error('Failed to delete card.')
      console.error(error)
    }
  }

  // CardType Actions
  async function fetchCardTypes() {
    try {
      cardTypes.value = await getCardTypes()
    } catch (error) {
      ElMessage.error('Failed to fetch card types.')
      console.error(error)
    }
  }
  
  // Available Models Actions
  async function fetchAvailableModels() {
    try {
      availableModels.value = await getContentModels()
    } catch (error) {
      ElMessage.error('Failed to fetch available content models.')
      console.error(error)
    }
  }

  // Utility
  function setActiveCard(cardId: number | null) {
    activeCardId.value = cardId
  }

  return {
    // State
    cards,
    cardTypes,
    availableModels,
    activeCardId,
    isLoading,
    // Getters
    cardTree,
    activeCard,
    // Actions
    fetchInitialData,
    fetchCards,
    addCard,
    modifyCard,
    removeCard,
    fetchCardTypes,
    fetchAvailableModels,
    setActiveCard,
  }
}) 