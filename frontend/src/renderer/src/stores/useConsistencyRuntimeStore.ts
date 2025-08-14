import { defineStore } from 'pinia'

interface ProjectRuntimeState {
  sinceCount: number
  lastCardId?: number
}

interface RuntimeState {
  byProject: Record<number, ProjectRuntimeState>
}

export const useConsistencyRuntimeStore = defineStore('consistencyRuntime', {
  state: (): RuntimeState => ({ byProject: {} }),
  actions: {
    load() {
      const raw = sessionStorage.getItem('consistency-runtime')
      if (raw) {
        try { this.byProject = JSON.parse(raw) } catch { this.byProject = {} }
      }
    },
    save() { sessionStorage.setItem('consistency-runtime', JSON.stringify(this.byProject)) },
    onChapterSaved(projectId: number, cardId: number, windowSize: number): boolean {
      if (!projectId || windowSize <= 0) return false
      const st = this.byProject[projectId] || { sinceCount: 0 }
      st.sinceCount = (st.sinceCount || 0) + 1
      st.lastCardId = cardId
      const hit = st.sinceCount >= windowSize
      if (hit) {
        st.sinceCount = 0
      }
      this.byProject[projectId] = st
      this.save()
      return hit
    },
    reset(projectId: number) {
      if (!projectId) return
      this.byProject[projectId] = { sinceCount: 0 }
      this.save()
    }
  }
}) 