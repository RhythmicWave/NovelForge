import { ref, watch, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import type { AssistantChatSession, AssistantPanelMessage } from '@renderer/types/assistantPanel'

interface UseAssistantSessionHistoryOptions {
  projectId: Ref<number | null | undefined>
  messages: Ref<AssistantPanelMessage[]>
  currentSession?: Ref<AssistantChatSession>
  historySessions?: Ref<AssistantChatSession[]>
  historyDrawerVisible?: Ref<boolean>
  onScrollToBottom?: () => void
}

function createEmptySession(projectId: number): AssistantChatSession {
  return {
    id: `session_${Date.now()}_${Math.random().toString(36).slice(2, 11)}`,
    projectId,
    title: '新对话',
    createdAt: Date.now(),
    updatedAt: Date.now(),
    messages: [],
  }
}

function getSessionStorageKey(projectId: number): string {
  return `assistant-sessions-${projectId}`
}

function getActiveSessionStorageKey(projectId: number): string {
  return `assistant-active-session-${projectId}`
}

function dedupeSessionsById(sessions: AssistantChatSession[]): AssistantChatSession[] {
  const seen = new Set<string>()
  const result: AssistantChatSession[] = []
  for (const item of sessions) {
    if (!item?.id || seen.has(item.id)) continue
    seen.add(item.id)
    result.push(item)
  }
  return result
}

export function useAssistantSessionHistory(options: UseAssistantSessionHistoryOptions) {
  const currentSession = options.currentSession ?? ref<AssistantChatSession>(createEmptySession(options.projectId.value || 0))
  const historySessions = options.historySessions ?? ref<AssistantChatSession[]>([])
  const historyDrawerVisible = options.historyDrawerVisible ?? ref(false)

  function readActiveSessionId(projectId: number): string | null {
    try {
      return localStorage.getItem(getActiveSessionStorageKey(projectId))
    } catch {
      return null
    }
  }

  function writeActiveSessionId(projectId: number, sessionId: string | null): void {
    try {
      const key = getActiveSessionStorageKey(projectId)
      if (!sessionId) {
        localStorage.removeItem(key)
        return
      }
      localStorage.setItem(key, sessionId)
    } catch {
      // ignore storage errors
    }
  }

  function loadHistorySessions(projectId: number): void {
    try {
      const key = getSessionStorageKey(projectId)
      const stored = localStorage.getItem(key)
      if (!stored) {
        historySessions.value = []
        return
      }
      const sessions = dedupeSessionsById(JSON.parse(stored) as AssistantChatSession[])
        .sort((a, b) => b.updatedAt - a.updatedAt)
      historySessions.value = sessions
      localStorage.setItem(key, JSON.stringify(sessions))
    } catch {
      historySessions.value = []
    }
  }

  function saveCurrentSession(): void {
    const projectId = options.projectId.value
    if (!projectId) return
    if (options.messages.value.length === 0) return

    try {
      const sessionToSave: AssistantChatSession = {
        ...currentSession.value,
        messages: JSON.parse(JSON.stringify(options.messages.value)),
        updatedAt: Date.now(),
        projectId,
      }

      if (sessionToSave.title === '新对话') {
        const firstUserMessage = options.messages.value.find(item => item.role === 'user')
        if (firstUserMessage) {
          sessionToSave.title =
            firstUserMessage.content.substring(0, 20) +
            (firstUserMessage.content.length > 20 ? '...' : '')
        }
      }

      const key = getSessionStorageKey(projectId)
      const stored = localStorage.getItem(key)
      const sessions = dedupeSessionsById(stored ? (JSON.parse(stored) as AssistantChatSession[]) : []).filter(
        session => session.id !== sessionToSave.id,
      )
      sessions.unshift(sessionToSave)

      if (sessions.length > 50) {
        sessions.splice(50)
      }

      localStorage.setItem(key, JSON.stringify(sessions))
      historySessions.value = sessions
      writeActiveSessionId(projectId, sessionToSave.id)

      if (currentSession.value.title !== sessionToSave.title) {
        currentSession.value.title = sessionToSave.title
      }
    } catch {
      // keep current UI state on localStorage failure
    }
  }

  function createNewSession(): void {
    if (options.messages.value.length > 0) {
      saveCurrentSession()
    }

    currentSession.value = createEmptySession(options.projectId.value || 0)
    options.messages.value = []
    historyDrawerVisible.value = false
    if (options.projectId.value) {
      writeActiveSessionId(options.projectId.value, currentSession.value.id)
    }
  }

  function loadSession(sessionId: string): void {
    if (sessionId === currentSession.value.id) return

    const session = historySessions.value.find(item => item.id === sessionId)
    if (!session) return

    if (options.messages.value.length > 0) {
      saveCurrentSession()
    }

    currentSession.value = { ...session }
    options.messages.value = [...session.messages]
    historyDrawerVisible.value = false
    options.onScrollToBottom?.()
    if (options.projectId.value) {
      writeActiveSessionId(options.projectId.value, currentSession.value.id)
    }
  }

  function deleteSession(sessionId: string): void {
    const projectId = options.projectId.value
    if (!projectId) return

    try {
      const key = getSessionStorageKey(projectId)
      historySessions.value = historySessions.value.filter(item => item.id !== sessionId)
      localStorage.setItem(key, JSON.stringify(historySessions.value))

      if (currentSession.value.id === sessionId) {
        const fallback = historySessions.value[0]
        if (fallback) {
          currentSession.value = { ...fallback }
          options.messages.value = [...fallback.messages]
          writeActiveSessionId(projectId, fallback.id)
        } else {
          currentSession.value = createEmptySession(projectId)
          options.messages.value = []
          writeActiveSessionId(projectId, currentSession.value.id)
        }
      } else {
        writeActiveSessionId(projectId, currentSession.value.id)
      }

      ElMessage.success('已删除会话')
    } catch {
      ElMessage.error('删除会话失败')
    }
  }

  function handleDeleteSession(sessionId: string): void {
    ElMessageBox.confirm('确定要删除这个对话吗？', '确认删除', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
      .then(() => {
        deleteSession(sessionId)
      })
      .catch(() => {
        // user canceled
      })
  }

  function formatSessionTime(timestamp: number): string {
    const now = Date.now()
    const diff = now - timestamp
    const minute = 60 * 1000
    const hour = 60 * minute
    const day = 24 * hour

    if (diff < minute) return '刚刚'
    if (diff < hour) return `${Math.floor(diff / minute)}分钟前`
    if (diff < day) return `${Math.floor(diff / hour)}小时前`
    if (diff < 7 * day) return `${Math.floor(diff / day)}天前`

    const date = new Date(timestamp)
    return `${date.getMonth() + 1}/${date.getDate()}`
  }

  watch(
    () => options.projectId.value,
    newProjectId => {
      if (!newProjectId) return
      loadHistorySessions(newProjectId)
      if (historySessions.value.length > 0) {
        const activeSessionId = readActiveSessionId(newProjectId)
        const targetSession = activeSessionId
          ? (historySessions.value.find(item => item.id === activeSessionId) || historySessions.value[0])
          : historySessions.value[0]

        currentSession.value = { ...targetSession }
        options.messages.value = [...targetSession.messages]
        writeActiveSessionId(newProjectId, targetSession.id)
        options.onScrollToBottom?.()
        return
      }

      currentSession.value = createEmptySession(newProjectId)
      options.messages.value = []
      writeActiveSessionId(newProjectId, currentSession.value.id)
    },
    { immediate: true },
  )

  return {
    currentSession,
    historySessions,
    historyDrawerVisible,
    saveCurrentSession,
    createNewSession,
    loadSession,
    handleDeleteSession,
    formatSessionTime,
  }
}
