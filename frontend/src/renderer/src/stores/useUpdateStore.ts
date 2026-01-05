/**
 * 更新检测状态管理 Store
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { ReleaseInfo, UpdateCheckResult } from '@renderer/services/updateService'
import { autoCheckForUpdates, manualCheckForUpdates, getCurrentVersion } from '@renderer/services/updateService'

export const useUpdateStore = defineStore('update', () => {
  // 当前版本
  const currentVersion = ref(getCurrentVersion())
  
  // 最新版本信息
  const latestVersion = ref<string | null>(null)
  const releaseInfo = ref<ReleaseInfo | null>(null)
  
  // 是否有可用更新
  const hasUpdate = computed(() => {
    return latestVersion.value !== null && releaseInfo.value !== null
  })
  
  // 检测状态
  const isChecking = ref(false)
  const lastCheckTime = ref<Date | null>(null)
  const lastCheckError = ref<string | null>(null)
  
  // 自动检测开关（持久化到 localStorage）
  const autoCheckEnabled = ref(true)
  
  // 初始化时从 localStorage 读取设置
  const STORAGE_KEY = 'novelforge_auto_update_enabled'
  const storedSetting = localStorage.getItem(STORAGE_KEY)
  if (storedSetting !== null) {
    autoCheckEnabled.value = storedSetting === 'true'
  }
  
  // 监听自动检测开关变化，同步到 localStorage
  function setAutoCheckEnabled(enabled: boolean) {
    autoCheckEnabled.value = enabled
    localStorage.setItem(STORAGE_KEY, String(enabled))
  }
  
  /**
   * 执行更新检测（内部方法）
   */
  async function performCheck(checkFn: () => Promise<UpdateCheckResult>): Promise<UpdateCheckResult> {
    isChecking.value = true
    lastCheckError.value = null
    
    try {
      const result = await checkFn()
      
      lastCheckTime.value = new Date()
      
      if (result.hasUpdate && result.releaseInfo) {
        latestVersion.value = result.latestVersion || null
        releaseInfo.value = result.releaseInfo
      } else {
        latestVersion.value = null
        releaseInfo.value = null
      }
      
      return result
    } catch (error: any) {
      lastCheckError.value = error.message || '检测失败'
      throw error
    } finally {
      isChecking.value = false
    }
  }
  
  /**
   * 自动检测更新（带重试）
   */
  async function autoCheck(): Promise<UpdateCheckResult> {
    return performCheck(autoCheckForUpdates)
  }
  
  /**
   * 手动检测更新（不重试）
   */
  async function manualCheck(): Promise<UpdateCheckResult> {
    return performCheck(manualCheckForUpdates)
  }
  
  /**
   * 清除更新状态（用户已知晓更新后可调用）
   */
  function clearUpdateNotification() {
    // 注意：这里不清除 latestVersion 和 releaseInfo，
    // 只是用于 UI 逻辑（比如关闭通知弹窗）
    // 如果需要真正清除，可以在这里实现
  }
  
  /**
   * 重置错误状态
   */
  function clearError() {
    lastCheckError.value = null
  }
  
  return {
    // 状态
    currentVersion,
    latestVersion,
    releaseInfo,
    hasUpdate,
    isChecking,
    lastCheckTime,
    lastCheckError,
    autoCheckEnabled,
    
    // 方法
    autoCheck,
    manualCheck,
    setAutoCheckEnabled,
    clearUpdateNotification,
    clearError
  }
})
