import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getProjects, type ProjectRead } from '@renderer/api/projects'
import { getCardsForProject, type CardRead } from '@renderer/api/cards'

export type InjectRef = { projectId: number; projectName: string; cardId: number; cardTitle: string; content: any; source?: 'auto' | 'manual' }

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
      if (injectedRefs.value.some(r => r.projectId === pid && r.cardId === id)) continue
      injectedRefs.value.push({ projectId: pid, projectName: pname, cardId: id, cardTitle: c.title, content: (c as any).content, source: 'manual' })
    }
  }

  function addInjectedRefDirect(ref: InjectRef, source: 'auto' | 'manual' = 'manual') {
    if (!ref) return
    const idx = injectedRefs.value.findIndex(r => r.projectId === ref.projectId && r.cardId === ref.cardId)
    const item: InjectRef = { ...ref, source }
    if (idx >= 0) injectedRefs.value[idx] = item
    else injectedRefs.value.push(item)
  }

  function clearAutoRefs() {
    injectedRefs.value = injectedRefs.value.filter(r => r.source !== 'auto')
  }

  function addAutoRef(ref: InjectRef) {
    clearAutoRefs()
    addInjectedRefDirect(ref, 'auto')
  }

  function removeInjectedRefAt(index: number) { injectedRefs.value.splice(index, 1) }
  function clearInjectedRefs() { injectedRefs.value = [] }

  return { projects, cardsByProject, injectedRefs, loadProjects, loadCardsForProject, addInjectedRefs, addInjectedRefDirect, addAutoRef, clearAutoRefs, removeInjectedRefAt, clearInjectedRefs }
}) 