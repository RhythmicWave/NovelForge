import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getProjects, type ProjectRead } from '@renderer/api/projects'
import { getCardsForProject, type CardRead } from '@renderer/api/cards'

export type InjectRef = { projectId: number; projectName: string; cardId: number; cardTitle: string; content: any; source?: 'auto' | 'manual' }
export type AssistantMessage = { role: 'user' | 'assistant'; content: string; ts?: number }

// 卡片上下文信息接口
export interface CardContextInfo {
  card_id: number
  title: string
  card_type: string
  parent_id: number | null
  project_id: number
  first_seen: number  // timestamp
  last_seen: number   // timestamp
  access_count: number
}

// 用户操作记录接口
export interface UserOperation {
  timestamp: number
  type: 'create' | 'edit' | 'delete'
  cardId: number
  cardTitle: string
  cardType: string
}

// 项目结构化上下文接口
export interface ProjectStructureContext {
  project_id: number
  project_name: string
  total_cards: number
  stats: Record<string, number>  // 卡片类型 -> 数量
  tree_text: string              // 树形文本
  available_card_types: string[] // 可用卡片类型
  last_updated: number           // 最后更新时间戳
  version: number                // 数据版本（用于缓存失效）
}

// 为避免开发/打包共用本地缓存，对话历史 key 加上环境前缀
// dev → 'development'，打包 → 'production'
const ENV_PREFIX = (import.meta as any)?.env?.MODE || 'production'
const HISTORY_KEY_PREFIX = `nf:${ENV_PREFIX}:assistant:history:`
const STRUCTURE_KEY_PREFIX = `nf:${ENV_PREFIX}:assistant:structure:`
const OPERATIONS_KEY_PREFIX = `nf:${ENV_PREFIX}:assistant:operations:`

function projectHistoryKey(projectId: number) { return `${HISTORY_KEY_PREFIX}${projectId}` }
function projectStructureKey(projectId: number) { return `${STRUCTURE_KEY_PREFIX}${projectId}` }
function projectOperationsKey(projectId: number) { return `${OPERATIONS_KEY_PREFIX}${projectId}` }

export const useAssistantStore = defineStore('assistant', () => {
  const projects = ref<ProjectRead[]>([])
  const cardsByProject = ref<Record<number, CardRead[]>>({})
  const injectedRefs = ref<InjectRef[]>([])
  
  const activeCardContext = ref<CardContextInfo | null>(null)
  const cardRegistry = ref<Map<number, CardContextInfo>>(new Map())
  const projectCardTypes = ref<string[]>([])
  
  // 项目结构化上下文
  const projectStructure = ref<ProjectStructureContext | null>(null)
  
  // 用户操作历史（最多3条）
  const recentOperations = ref<UserOperation[]>([])

  async function loadProjects() {
    projects.value = await getProjects()
  }

  async function loadCardsForProject(pid: number) {
    const list = await getCardsForProject(pid)
    cardsByProject.value[pid] = list
    return list
  }

  function addInjectedRefs(pid: number, pname: string, ids: number[]) {
    const list = cardsByProject.value[pid] || []
    const map = new Map<number, CardRead>()
    list.forEach(c => map.set(c.id, c))
    for (const id of ids) {
      const c = map.get(id)
      if (!c) continue
      const existingIdx = injectedRefs.value.findIndex(r => r.projectId === pid && r.cardId === id)
      if (existingIdx >= 0) {
        // 升级为 manual（若原为 auto）并刷新标题/内容
        const prev = injectedRefs.value[existingIdx]
        injectedRefs.value[existingIdx] = { ...prev, projectName: pname, cardTitle: c.title, content: (c as any).content, source: 'manual' }
        continue
      }
      injectedRefs.value.push({ projectId: pid, projectName: pname, cardId: id, cardTitle: c.title, content: (c as any).content, source: 'manual' })
    }
  }

  function addInjectedRefDirect(ref: InjectRef, source: 'auto' | 'manual' = 'manual') {
    if (!ref) return
    const idx = injectedRefs.value.findIndex(r => r.projectId === ref.projectId && r.cardId === ref.cardId)
    const prev = idx >= 0 ? injectedRefs.value[idx] : null
    // 规则：manual 永远不被 auto 覆盖；manual 会覆盖 auto；同源则更新内容
    if (idx >= 0) {
      if (prev?.source === 'manual' && source === 'auto') {
        // 保留 manual，不做降级，仅更新显示信息/内容
        injectedRefs.value[idx] = { ...prev, projectName: ref.projectName, cardTitle: ref.cardTitle, content: ref.content, source: 'manual' }
        return
      }
      injectedRefs.value[idx] = { ...prev, ...ref, source }
    } else {
      injectedRefs.value.push({ ...ref, source })
    }
  }

  function clearAutoRefs() {
    injectedRefs.value = injectedRefs.value.filter(r => r.source !== 'auto')
  }

  function addAutoRef(ref: InjectRef) {
    // 仅清除其他 auto；若相同卡片已被标记为 manual，则不会被覆盖
    clearAutoRefs()
    addInjectedRefDirect(ref, 'auto')
  }

  function removeInjectedRefAt(index: number) { injectedRefs.value.splice(index, 1) }
  function clearInjectedRefs() { injectedRefs.value = [] }

  // --- 对话历史（按项目持久化到 localStorage）---
  function getHistory(projectId: number): AssistantMessage[] {
    try {
      const raw = localStorage.getItem(projectHistoryKey(projectId))
      if (!raw) return []
      const arr = JSON.parse(raw)
      if (!Array.isArray(arr)) return []
      return arr as AssistantMessage[]
    } catch { return [] }
  }

  function setHistory(projectId: number, history: AssistantMessage[]) {
    try {
      localStorage.setItem(projectHistoryKey(projectId), JSON.stringify(history || []))
    } catch {}
  }

  function appendHistory(projectId: number, msg: AssistantMessage) {
    const hist = getHistory(projectId)
    hist.push({ ...msg, ts: msg.ts ?? Date.now() })
    setHistory(projectId, hist)
  }

  function clearHistory(projectId: number) {
    try { localStorage.removeItem(projectHistoryKey(projectId)) } catch {}
  }
  
  // 卡片上下文管理方法
  function updateActiveCard(card: CardRead | null, projectId: number) {
    if (!card) {
      activeCardContext.value = null
      console.log('📋 [AssistantStore] 清空活动卡片')
      return
    }
    
    const now = Date.now()
    const info: CardContextInfo = {
      card_id: card.id,
      title: card.title,
      card_type: (card as any).card_type?.name || 'Unknown',  // 修复：使用 card_type.name
      parent_id: (card as any).parent_id || null,
      project_id: projectId,
      first_seen: now,
      last_seen: now,
      access_count: 1
    }
    
    console.log('📋 [AssistantStore] 更新活动卡片:', info)
    
    // 更新活动卡片
    activeCardContext.value = info
    
    // 注册到卡片注册表（如果已存在则更新访问信息）
    registerCard(info)
  }
  
  function registerCard(info: CardContextInfo) {
    const existing = cardRegistry.value.get(info.card_id)
    if (existing) {
      // 更新已存在的卡片信息
      cardRegistry.value.set(info.card_id, {
        ...existing,
        title: info.title,  // 更新标题（可能改变）
        card_type: info.card_type,
        last_seen: Date.now(),
        access_count: existing.access_count + 1
      })
    } else {
      // 新卡片
      cardRegistry.value.set(info.card_id, info)
    }
  }
  
  function updateProjectCardTypes(types: string[]) {
    projectCardTypes.value = types
  }
  
  function getContextForAssistant(): {
    active_card: CardContextInfo | null
    recent_cards: CardContextInfo[]
    card_types: string[]
  } {
    // 获取最近访问的卡片（最多10个，按last_seen排序）
    const recent = Array.from(cardRegistry.value.values())
      .sort((a, b) => b.last_seen - a.last_seen)
      .slice(0, 10)
    
    return {
      active_card: activeCardContext.value,
      recent_cards: recent,
      card_types: projectCardTypes.value
    }
  }
  
  function clearCardContext() {
    activeCardContext.value = null
    cardRegistry.value.clear()
    projectCardTypes.value = []
  }
  
  //  ========== 项目结构化上下文管理 ==========
  
  /**
   * 从 localStorage 加载项目结构缓存
   */
  function loadProjectStructureFromCache(projectId: number): ProjectStructureContext | null {
    try {
      const raw = localStorage.getItem(projectStructureKey(projectId))
      if (!raw) return null
      const data = JSON.parse(raw)
      return data as ProjectStructureContext
    } catch {
      return null
    }
  }
  
  /**
   * 保存项目结构到 localStorage
   */
  function saveProjectStructureToCache(structure: ProjectStructureContext) {
    try {
      localStorage.setItem(projectStructureKey(structure.project_id), JSON.stringify(structure))
    } catch (e) {
      console.warn('保存项目结构缓存失败', e)
    }
  }
  
  /**
   * 构建卡片树形文本（递归）
   */
  function buildCardTreeText(cards: CardRead[], parentId: number | null = null, depth: number = 0, currentCardId?: number): string {
    const indent = depth === 0 ? '' : '│  '.repeat(depth - 1) + '├─ '
    const children = cards.filter(c => (c as any).parent_id === parentId)
      .sort((a, b) => ((a as any).display_order || 0) - ((b as any).display_order || 0))
    
    const lines: string[] = []
    
    for (let i = 0; i < children.length; i++) {
      const card = children[i]
      const typeName = (card as any).card_type?.name || 'Unknown'
      const updatedAt = (card as any).updated_at
      const updatedDate = updatedAt ? new Date(updatedAt).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }) : ''
      const isCurrent = currentCardId && card.id === currentCardId
      const marker = isCurrent ? ' ⭐当前' : ''
      
      lines.push(`${indent}[${typeName}] ${card.title} {id:${card.id} | 更新:${updatedDate}${marker}}`)
      
      // 递归处理子卡片
      const childText = buildCardTreeText(cards, card.id, depth + 1, currentCardId)
      if (childText) {
        lines.push(childText)
      }
    }
    
    return lines.join('\n')
  }
  
  /**
   * 从卡片数据生成项目结构化上下文
   * @param projectId 项目ID
   * @param projectName 项目名称
   * @param cards 所有卡片数据（来自 useCardStore）
   * @param cardTypes 所有卡片类型（来自 useCardStore）
   * @param currentCardId 当前激活的卡片ID（可选）
   */
  function buildProjectStructure(
    projectId: number,
    projectName: string,
    cards: CardRead[],
    cardTypes: any[],
    currentCardId?: number
  ): ProjectStructureContext {
    // 统计各类型卡片数量
    const stats: Record<string, number> = {}
    for (const card of cards) {
      const typeName = (card as any).card_type?.name || '未分类'
      stats[typeName] = (stats[typeName] || 0) + 1
    }
    
    // 生成树形文本
    const treeText = buildCardTreeText(cards, null, 0, currentCardId)
    
    // 可用卡片类型
    const availableTypes = cardTypes.map(ct => ct.name)
    
    return {
      project_id: projectId,
      project_name: projectName,
      total_cards: cards.length,
      stats,
      tree_text: treeText || 'ROOT\n(暂无卡片)',
      available_card_types: availableTypes,
      last_updated: Date.now(),
      version: cards.length  // 简单用卡片数量作为版本号
    }
  }
  
  /**
   * 更新项目结构（自动构建+缓存）
   * @param projectId 项目ID
   * @param projectName 项目名称
   * @param cards 所有卡片数据
   * @param cardTypes 所有卡片类型
   * @param currentCardId 当前卡片ID
   * @param forceRebuild 是否强制重建（忽略缓存）
   */
  function updateProjectStructure(
    projectId: number,
    projectName: string,
    cards: CardRead[],
    cardTypes: any[],
    currentCardId?: number,
    forceRebuild: boolean = false
  ) {
    // 检查缓存是否有效
    if (!forceRebuild) {
      const cached = loadProjectStructureFromCache(projectId)
      if (cached && cached.version === cards.length) {
        // 缓存有效，直接使用（但更新当前卡片标记）
        const updated = buildProjectStructure(projectId, projectName, cards, cardTypes, currentCardId)
        projectStructure.value = updated
        saveProjectStructureToCache(updated)
        console.log('📋 [AssistantStore] 使用缓存的项目结构（已更新当前卡片）')
        return
      }
    }
    
    // 重新构建
    const structure = buildProjectStructure(projectId, projectName, cards, cardTypes, currentCardId)
    projectStructure.value = structure
    saveProjectStructureToCache(structure)
    console.log('📋 [AssistantStore] 已构建项目结构:', structure)
  }
  
  /**
   * 清除项目结构缓存
   */
  function clearProjectStructure() {
    projectStructure.value = null
  }
  
  // ========== 用户操作历史管理 ==========
  
  /**
   * 从 localStorage 加载操作历史
   */
  function loadOperationsFromCache(projectId: number): UserOperation[] {
    try {
      const raw = localStorage.getItem(projectOperationsKey(projectId))
      if (!raw) return []
      const arr = JSON.parse(raw)
      if (!Array.isArray(arr)) return []
      return arr as UserOperation[]
    } catch {
      return []
    }
  }
  
  /**
   * 保存操作历史到 localStorage
   */
  function saveOperationsToCache(projectId: number, operations: UserOperation[]) {
    try {
      localStorage.setItem(projectOperationsKey(projectId), JSON.stringify(operations))
    } catch (e) {
      console.warn('保存操作历史失败', e)
    }
  }
  
  /**
   * 记录用户操作
   */
  function recordOperation(projectId: number, op: Omit<UserOperation, 'timestamp'>) {
    const operation: UserOperation = {
      ...op,
      timestamp: Date.now()
    }
    
    // 添加到内存
    recentOperations.value.unshift(operation)
    
    // 保持最多3条
    if (recentOperations.value.length > 3) {
      recentOperations.value = recentOperations.value.slice(0, 3)
    }
    
    // 保存到缓存
    saveOperationsToCache(projectId, recentOperations.value)
    
    console.log('📝 [AssistantStore] 记录操作:', operation)
  }
  
  /**
   * 加载操作历史
   */
  function loadOperations(projectId: number) {
    recentOperations.value = loadOperationsFromCache(projectId)
  }
  
  /**
   * 格式化操作历史为文本
   */
  function formatRecentOperations(): string {
    if (recentOperations.value.length === 0) return ''
    
    const lines = recentOperations.value.map((op, idx) => {
      const time = new Date(op.timestamp).toLocaleString('zh-CN', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
      })
      const emoji = op.type === 'create' ? '➕' : op.type === 'edit' ? '✏️' : '🗑️'
      const action = op.type === 'create' ? '创建' : op.type === 'edit' ? '编辑' : '删除'
      return `${idx + 1}. [${time}] ${emoji} ${action} "${op.cardTitle}" (${op.cardType} #${op.cardId})`
    })
    
    return lines.join('\n')
  }
  
  /**
   * 清除操作历史
   */
  function clearOperations(projectId: number) {
    recentOperations.value = []
    try {
      localStorage.removeItem(projectOperationsKey(projectId))
    } catch {}
  }

  return { 
    projects, cardsByProject, injectedRefs, 
    loadProjects, loadCardsForProject, 
    addInjectedRefs, addInjectedRefDirect, addAutoRef, clearAutoRefs, removeInjectedRefAt, clearInjectedRefs, 
    getHistory, setHistory, appendHistory, clearHistory,
    // 卡片上下文方法
    updateActiveCard, registerCard, updateProjectCardTypes, getContextForAssistant, clearCardContext,
    activeCardContext, cardRegistry, projectCardTypes,
    // 项目结构化上下文方法
    projectStructure,
    updateProjectStructure,
    clearProjectStructure,
    //  操作历史方法
    recentOperations,
    recordOperation,
    loadOperations,
    formatRecentOperations,
    clearOperations
  }
}) 