import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getProjects, type ProjectRead } from '@renderer/api/projects'
import { getCardsForProject, type CardRead } from '@renderer/api/cards'

export type InjectRef = { projectId: number; projectName: string; cardId: number; cardTitle: string; content: any; source?: 'auto' | 'manual' }
export type AssistantMessage = { role: 'user' | 'assistant'; content: string; ts?: number }

// 为避免开发/打包共用本地缓存，对话历史 key 加上环境前缀
// dev → 'development'，打包 → 'production'
const ENV_PREFIX = (import.meta as any)?.env?.MODE || 'production'
const HISTORY_KEY_PREFIX = `nf:${ENV_PREFIX}:assistant:history:`
function projectHistoryKey(projectId: number) { return `${HISTORY_KEY_PREFIX}${projectId}` }

export const useAssistantStore = defineStore('assistant', () => {
  const projects = ref<ProjectRead[]>([])
  const cardsByProject = ref<Record<number, CardRead[]>>({})
  const injectedRefs = ref<InjectRef[]>([])

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

  return { projects, cardsByProject, injectedRefs, loadProjects, loadCardsForProject, addInjectedRefs, addInjectedRefDirect, addAutoRef, clearAutoRefs, removeInjectedRefAt, clearInjectedRefs, getHistory, setHistory, appendHistory, clearHistory }
}) 