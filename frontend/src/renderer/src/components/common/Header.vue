<script setup lang="ts">
import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { Setting, Sunny, Moon, Collection } from '@element-plus/icons-vue'
import { useAppStore } from '@renderer/stores/useAppStore'
import KnowledgeManager from './KnowledgeManager.vue'

const appStore = useAppStore()
const { currentView, isDarkMode } = storeToRefs(appStore)

function toggleTheme() {
  appStore.toggleTheme()
}

function openSettingsDialog() {
  appStore.openSettings()
}

function handleLogoClick() {
  if (currentView.value === 'editor') {
    appStore.goToDashboard()
  }
}

const isLogoClickable = computed(() => currentView.value === 'editor')

// 知识库抽屉
const kbVisible = ref(false)
</script>

<template>
  <header class="app-header">
    <div class="logo-container" @click="handleLogoClick" :class="{ clickable: isLogoClickable }">
      <span class="logo-text">Novel Forge</span>
    </div>
    <div class="actions-container">
      <el-button :icon="Collection" @click="kbVisible = true" circle title="知识库" />
      <el-button :icon="isDarkMode ? Moon : Sunny" @click="toggleTheme" circle title="切换主题" />
      <el-button :icon="Setting" @click="openSettingsDialog" circle title="设置" />
    </div>
    <el-drawer v-model="kbVisible" title="知识库" size="50%" append-to-body>
      <KnowledgeManager />
    </el-drawer>
  </header>
</template>

<style scoped>
.app-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 20px;
  height: 60px;
  background-color: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color);
  flex-shrink: 0; /* Prevent header from shrinking */
}

.logo-container.clickable {
  cursor: pointer;
  transition: opacity 0.2s;
}

.logo-container.clickable:hover {
  opacity: 0.8;
}

.logo-container .logo-text {
  font-size: 20px;
  font-weight: bold;
  color: var(--el-text-color-primary);
}

.actions-container {
  display: flex;
  gap: 15px;
}
</style> 