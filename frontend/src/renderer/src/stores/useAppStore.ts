import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useAppStore = defineStore('app', () => {
  // 当前视图
  const currentView = ref<'dashboard' | 'editor'>('dashboard')
  
  // 主题状态
  const isDarkMode = ref(false)
  
  // 设置对话框状态
  const settingsDialogVisible = ref(false)
  
  // 全局加载状态
  const globalLoading = ref(false)
  
  // 全局错误状态
  const globalError = ref<string | null>(null)

  // Computed
  const isDashboard = computed(() => currentView.value === 'dashboard')
  const isEditor = computed(() => currentView.value === 'editor')

  // Actions
  function setCurrentView(view: 'dashboard' | 'editor') {
    currentView.value = view
  }

  function goToDashboard() {
    currentView.value = 'dashboard'
  }

  function goToEditor() {
    currentView.value = 'editor'
  }

  function toggleTheme() {
    isDarkMode.value = !isDarkMode.value
    localStorage.setItem('theme', isDarkMode.value ? 'dark' : 'light')
    applyTheme()
  }

  function setTheme(dark: boolean) {
    isDarkMode.value = dark
    localStorage.setItem('theme', dark ? 'dark' : 'light')
    applyTheme()
  }

  function applyTheme() {
    const html = document.documentElement
    if (isDarkMode.value) {
      html.classList.add('dark')
    } else {
      html.classList.remove('dark')
    }
  }

  function initTheme() {
    const savedTheme = localStorage.getItem('theme')
    isDarkMode.value = savedTheme === 'dark'
    applyTheme()
  }

  function openSettings() {
    settingsDialogVisible.value = true
  }

  function closeSettings() {
    settingsDialogVisible.value = false
  }

  function setGlobalLoading(loading: boolean) {
    globalLoading.value = loading
  }

  function setGlobalError(error: string | null) {
    globalError.value = error
  }

  function clearGlobalError() {
    globalError.value = null
  }

  function reset() {
    currentView.value = 'dashboard'
    settingsDialogVisible.value = false
    globalLoading.value = false
    globalError.value = null
  }

  return {
    // State
    currentView,
    isDarkMode,
    settingsDialogVisible,
    globalLoading,
    globalError,
    
    // Computed
    isDashboard,
    isEditor,
    
    // Actions
    setCurrentView,
    goToDashboard,
    goToEditor,
    toggleTheme,
    setTheme,
    applyTheme,
    initTheme,
    openSettings,
    closeSettings,
    setGlobalLoading,
    setGlobalError,
    clearGlobalError,
    reset
  }
}) 