<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useUpdateStore } from '@renderer/stores/useUpdateStore'
import { ElMessage } from 'element-plus'
import { Refresh, Download } from '@element-plus/icons-vue'

const updateStore = useUpdateStore()

// 此处原本有 Electron 运行环境信息展示，现按需求移除，仅保留更新相关内容

// 手动检测更新
const handleManualCheck = async () => {
  try {
    const result = await updateStore.manualCheck()
    if (result.hasUpdate) {
      ElMessage.success(`发现新版本 v${result.latestVersion}！`)
    } else {
      ElMessage.info('当前已是最新版本')
    }
  } catch (error: any) {
    ElMessage.error(error.message || '检测失败，请检查网络连接')
  }
}

// 切换自动检测
const handleAutoCheckToggle = (value: boolean) => {
  updateStore.setAutoCheckEnabled(value)
  ElMessage.success(value ? '已开启自动检测更新' : '已关闭自动检测更新')
}

// 打开 Release 页面
const openReleasePage = () => {
  if (updateStore.releaseInfo?.htmlUrl) {
    window.open(updateStore.releaseInfo.htmlUrl, '_blank')
  }
}

// 格式化时间
const formatTime = (date: Date | null) => {
  if (!date) return '从未检测'
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  }).format(date)
}
</script>

<template>
  <div class="about-page">
    <!-- 当前版本信息 -->
    <el-card shadow="never" class="version-card">
      <template #header>
        <div class="card-header">
          <span>当前版本</span>
        </div>
      </template>
      <div class="version-info">
        <div class="version-number">{{ updateStore.currentVersion }}</div>
        <div class="version-meta">
          <div v-if="updateStore.lastCheckTime" class="last-check">
            上次检测：{{ formatTime(updateStore.lastCheckTime) }}
          </div>
        </div>
      </div>
    </el-card>

    <!-- 自动更新设置 -->
    <el-card shadow="never" class="update-settings-card">
      <template #header>
        <div class="card-header">
          <span>更新设置</span>
        </div>
      </template>
      <div class="settings-row">
        <div class="setting-item">
          <span class="setting-label">自动检测更新</span>
          <el-switch
            :model-value="updateStore.autoCheckEnabled"
            @change="handleAutoCheckToggle"
          />
        </div>
        <div class="setting-item">
          <span class="setting-label">手动检测</span>
          <el-button
            type="primary"
            :icon="Refresh"
            :loading="updateStore.isChecking"
            @click="handleManualCheck"
          >
            {{ updateStore.isChecking ? '检测中...' : '检测更新' }}
          </el-button>
        </div>
      </div>
    </el-card>

    <!-- 最新版本信息：标题 + Release note 文本 + 查看详情按钮 -->
    <el-card v-if="updateStore.hasUpdate" shadow="never" class="new-version-card">
      <template #header>
        <div class="card-header">
          <span>最新 Release</span>
          <el-tag type="warning" effect="dark">v{{ updateStore.latestVersion }}</el-tag>
        </div>
      </template>
      <div class="release-info">
        <div class="release-meta">
          <span class="release-name">{{ updateStore.releaseInfo?.name }}</span>
          <el-button
            type="primary"
            size="small"
            :icon="Download"
            @click="openReleasePage"
          >
            查看详情
          </el-button>
        </div>
        <div class="release-notes">
          <div class="notes-title">更新内容：</div>
          <div class="notes-content">{{ updateStore.releaseInfo?.body || '暂无更新说明' }}</div>
        </div>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.about-page {
  padding: 20px;
  max-width: 900px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
}

.version-card .version-info {
  text-align: center;
  padding: 20px 0;
}

.version-number {
  font-size: 48px;
  font-weight: 700;
  color: var(--el-color-primary);
  margin-bottom: 12px;
}

.version-meta {
  color: var(--el-text-color-secondary);
  font-size: 14px;
}

.update-settings-card .settings-row {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.setting-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.setting-item:last-child {
  border-bottom: none;
}

.setting-label {
  font-size: 14px;
  color: var(--el-text-color-regular);
}

.new-version-card {
  border: 2px solid var(--el-color-warning);
}

.release-info {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.release-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.release-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.release-notes {
  background-color: var(--el-fill-color-lighter);
  border-radius: 6px;
  padding: 16px;
}

.notes-title {
  font-weight: 600;
  margin-bottom: 12px;
  color: var(--el-text-color-primary);
}

.notes-content {
  color: var(--el-text-color-regular);
  line-height: 1.6;
  white-space: pre-line; /* 按换行符断行，合并多空格 */
  max-height: 200px;
  overflow-y: auto;
  font-size: 14px;
}

.runtime-card .versions li:last-child {
  border-bottom: none;
}
</style>
