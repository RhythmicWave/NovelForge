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
  type CardUpdate,
} from '@renderer/api/cards'
import { useProjectStore } from './useProjectStore'
import { ElMessage } from 'element-plus'
import { BASE_URL } from '@renderer/api/request'

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

  // 新增：addCard 支持 options.silent，静默模式下不全量刷新、不弹 Toast，直接本地插入并返回新卡
  async function addCard(cardData: CardCreate, options?: { silent?: boolean }) {
    if (!currentProject.value?.id) return
    try {
      const newCard = await createCard(currentProject.value.id, cardData)
      if (options?.silent) {
        // 直接插入本地状态，避免频繁全量刷新导致的 "加载中" 卡住
        cards.value = [...cards.value, newCard as unknown as CardRead]
      } else {
        await fetchCards(currentProject.value.id)
        ElMessage.success(`Card "${newCard.title}" created.`)
      }
      return newCard
    } catch (error) {
      if (!options?.silent) ElMessage.error('Failed to create card.')
      console.error(error)
      return
    }
  }

  // 增加可选参数：skipHooks 用于内部更新时跳过“保存后钩子”
  async function modifyCard(cardId: number, cardData: { content: Record<string, any> | null } | CardUpdate, options?: { skipHooks?: boolean }) {
    try {
      console.log('[CardStore] 准备更新卡片:', cardId, cardData)
      // 使用原始响应以读取头部 X-Workflows-Started
      const axiosResp: any = await (await import('@renderer/api/cards')).updateCardRaw(cardId, cardData as CardUpdate)
      const updatedCard: CardRead = axiosResp.data
      console.log('[CardStore] 更新卡片成功，检查工作流回执响应头:', axiosResp.headers)

      // 本地同步更新
      if ('parent_id' in cardData || 'display_order' in cardData) {
        if (currentProject.value?.id) await fetchCards(currentProject.value.id)
      } else {
        const index = cards.value.findIndex((c) => c.id === cardId)
        if (index !== -1) {
          const existingCard = cards.value[index]
          const newContent = (cardData as any).content !== undefined ? (cardData as any).content : existingCard.content
          cards.value[index] = { ...existingCard, ...updatedCard, content: newContent }
        }
      }
      ElMessage.success(`Card "${updatedCard.title}" updated.`)

      // 读取工作流运行回执并订阅事件，完成后刷新
      const hdr = axiosResp.headers || {}
      const runHeader: string | undefined = hdr['x-workflows-started'] || hdr['X-Workflows-Started'] || hdr['x-workflows-started'.toLowerCase()]
      const runIds: number[] = typeof runHeader === 'string' && runHeader.trim()
        ? runHeader.split(',').map((s: string) => Number(s.trim())).filter((n: number) => Number.isFinite(n))
        : []
      console.log('[Workflow] 工作流启动回执 runIds =', runIds)

      // 兜底轮询函数
      const pollUntilDone = async (runId: number, maxSecs = 30) => {
        const start = Date.now()
        while (Date.now() - start < maxSecs * 1000) {
          try {
            const resp = await fetch(`${BASE_URL}/api/workflows/runs/${runId}`, { method: 'GET' })
            const json = await resp.json()
            const st = json?.status
            console.log(`[Workflow] 轮询状态 run_id=${runId} status=${st}`)
            if (st === 'succeeded' || st === 'failed' || st === 'cancelled') {
              if (currentProject.value?.id) await fetchCards(currentProject.value.id)
              return
            }
          } catch (e) { console.warn('[Workflow] 轮询异常，将继续重试', e) }
          await new Promise(r => setTimeout(r, 1000))
        }
      }

      if (runIds.length && currentProject.value?.id) {
        for (const rid of runIds) {
          try {
            console.log(`[Workflow] 开始订阅 SSE 事件 run_id=${rid} ...`)
            const es = new EventSource(`${BASE_URL}/api/workflows/runs/${rid}/events`)
            let finished = false
            es.onopen = () => console.log(`[Workflow] SSE 已连接 run_id=${rid}`)
            es.onmessage = (evt) => console.log(`[Workflow] 默认消息 run_id=${rid}:`, evt.data)
            es.addEventListener('step_started', (evt: MessageEvent) => console.log(`[Workflow] 步骤开始 run_id=${rid}:`, evt.data))
            es.addEventListener('step_succeeded', (evt: MessageEvent) => console.log(`[Workflow] 步骤成功 run_id=${rid}:`, evt.data))
            es.addEventListener('step_failed', (evt: MessageEvent) => console.warn(`[Workflow] 步骤失败 run_id=${rid}:`, evt.data))
            es.addEventListener('run_completed', async (evt: MessageEvent) => {
              console.log(`[Workflow] 运行完成 run_id=${rid}:`, evt.data)
              finished = true
              try {
                const payload = (() => { try { return JSON.parse(String(evt.data || '{}')) } catch { return {} } })()
                const affected: number[] = Array.isArray(payload?.affected_card_ids) ? payload.affected_card_ids.filter((n: any) => Number.isFinite(Number(n))).map((n: any) => Number(n)) : []
                if (affected.length > 0) {
                  // 精准刷新：按受影响卡片拉取详情并合并到本地
                  for (const cid of affected) {
                    try {
                      const resp = await fetch(`${BASE_URL}/api/cards/${cid}`, { method: 'GET' })
                      if (resp.ok) {
                        const updated = await resp.json()
                        const i = cards.value.findIndex(c => c.id === cid)
                        if (i >= 0) {
                          const prev = cards.value[i]
                          cards.value[i] = { ...prev, ...updated, content: updated?.content ?? prev.content }
                        } else {
                          // 若本地列表没有该卡，退化为全量刷新
                          if (currentProject.value?.id) await fetchCards(currentProject.value.id)
                        }
                      }
                    } catch (e) { console.warn('[Workflow] 刷新受影响卡片失败', cid, e) }
                  }
                } else {
                  // 没有携带受影响集合，回退为全量刷新
                  if (currentProject.value?.id) await fetchCards(currentProject.value.id)
                }
              } finally { es.close() }
            })
            es.onerror = async (err) => {
              if (finished) {
                console.log(`[Workflow] SSE 已正常结束 run_id=${rid}`)
                es.close()
                return
              }
              console.warn(`[Workflow] SSE 出错/断开 run_id=${rid}，启动轮询兜底`, err)
              es.close()
              await pollUntilDone(rid)
            }
          } catch (e) {
            console.warn('[Workflow] 打开 SSE 失败，将直接轮询', e)
            await pollUntilDone(rid)
          }
        }
      }

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