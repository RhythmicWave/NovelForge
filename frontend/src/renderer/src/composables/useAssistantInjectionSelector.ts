import { computed, ref, type Ref } from 'vue'
import type { CardRead } from '@renderer/api/cards'

interface AssistantProjectLite {
  id: number
  name: string
}

interface AssistantInjectionStore {
  projects: AssistantProjectLite[]
  loadProjects: () => Promise<void>
  loadCardsForProject: (pid: number) => Promise<CardRead[]>
  addInjectedRefs: (pid: number, projectName: string, ids: number[]) => void
}

interface UseAssistantInjectionSelectorOptions {
  assistantStore: AssistantInjectionStore
  currentProjectId: Ref<number | null | undefined>
}

export function useAssistantInjectionSelector(options: UseAssistantInjectionSelectorOptions) {
  const selectorVisible = ref(false)
  const selectorSourcePid = ref<number | null>(null)
  const selectorCards = ref<CardRead[]>([])
  const selectorSearch = ref('')
  const selectorSelectedIds = ref<number[]>([])
  const selectorCheckedKeys = ref<string[]>([])

  const filteredSelectorCards = computed(() => {
    const query = (selectorSearch.value || '').trim().toLowerCase()
    if (!query) return selectorCards.value
    return (selectorCards.value || []).filter(card => (card.title || '').toLowerCase().includes(query))
  })

  const selectorTreeData = computed(() => {
    const cardsByType: Record<string, any[]> = {}
    for (const card of filteredSelectorCards.value || []) {
      const typeName = card.card_type?.name || '未分类'
      if (!cardsByType[typeName]) {
        cardsByType[typeName] = []
      }
      cardsByType[typeName].push({
        id: card.id,
        title: card.title,
        label: card.title,
        key: `card:${card.id}`,
        isLeaf: true,
      })
    }

    return Object.keys(cardsByType)
      .sort()
      .map((typeName, idx) => ({
        key: `type:${idx}`,
        label: typeName,
        children: cardsByType[typeName],
      }))
  })

  async function openInjectSelector() {
    await options.assistantStore.loadProjects()
    selectorSourcePid.value = options.currentProjectId.value ?? (options.assistantStore.projects[0]?.id ?? null)
    selectorCards.value = selectorSourcePid.value
      ? await options.assistantStore.loadCardsForProject(selectorSourcePid.value)
      : []
    selectorSelectedIds.value = []
    selectorCheckedKeys.value = []
    selectorSearch.value = ''
    selectorVisible.value = true
  }

  async function onSelectorProjectChange(pid: number | null) {
    selectorCards.value = []
    selectorSelectedIds.value = []
    selectorCheckedKeys.value = []
    if (!pid) return
    selectorCards.value = await options.assistantStore.loadCardsForProject(pid)
  }

  function onTreeCheck(_: any, meta: any) {
    const keys: string[] = (meta?.checkedKeys || []) as string[]
    selectorCheckedKeys.value = keys
    selectorSelectedIds.value = keys
      .filter(key => key.startsWith('card:'))
      .map(key => Number(key.split(':')[1]))
      .filter(id => Number.isFinite(id))
  }

  function confirmAddInjectedRefs() {
    const projectId = selectorSourcePid.value
    if (!projectId || selectorSelectedIds.value.length === 0) {
      selectorVisible.value = false
      return
    }
    const projectName = options.assistantStore.projects.find(project => project.id === projectId)?.name || ''
    options.assistantStore.addInjectedRefs(projectId, projectName, selectorSelectedIds.value)
    selectorVisible.value = false
  }

  return {
    selectorVisible,
    selectorSourcePid,
    selectorCards,
    selectorSearch,
    selectorSelectedIds,
    selectorCheckedKeys,
    selectorTreeData,
    openInjectSelector,
    onSelectorProjectChange,
    onTreeCheck,
    confirmAddInjectedRefs,
  }
}
