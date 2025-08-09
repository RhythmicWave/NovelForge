<script setup lang="ts">
import { onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import Dashboard from './views/Dashboard.vue'
import Editor from './views/Editor.vue'
import Header from './components/common/Header.vue'
import SettingsDialog from './components/common/SettingsDialog.vue'
import { useAppStore } from './stores/useAppStore'
import { useProjectStore } from './stores/useProjectStore'
import type { components } from '@renderer/types/generated'
import { schemaService } from '@renderer/api/schema'

type Project = components['schemas']['ProjectRead']

const appStore = useAppStore()
const projectStore = useProjectStore()

const { currentView, settingsDialogVisible } = storeToRefs(appStore)
const { currentProject } = storeToRefs(projectStore)

function handleProjectSelected(project: Project) {
  projectStore.setCurrentProject(project)
  appStore.goToEditor()
}

function handleBackToDashboard() {
  projectStore.reset()
  appStore.goToDashboard()
}

function handleOpenSettings() {
  appStore.openSettings()
}

function handleCloseSettings() {
  appStore.closeSettings()
}

// 初始化主题和加载全局资源
onMounted(() => {
  appStore.initTheme()
  schemaService.loadSchemas() // Load all schemas on app startup
})
</script>

<template>
  <div class="app-layout">
    <Header />
    <main class="main-content">
      <Dashboard v-if="currentView === 'dashboard'" @project-selected="handleProjectSelected" />
      <Editor
        v-else-if="currentView === 'editor' && currentProject"
        :initial-project="currentProject"
        @back-to-dashboard="handleBackToDashboard"
      />
    </main>
    <SettingsDialog 
      v-model="settingsDialogVisible"
      @close="handleCloseSettings"
    />
  </div>
</template>

<style scoped>
.app-layout {
  display: flex;
  flex-direction: column;
  height: 100vh;
  width: 100vw;
  overflow: hidden;
  background-color: var(--el-bg-color-page);
}

.main-content {
  flex-grow: 1;
  overflow: auto; /* Allow content to scroll if needed */
}
</style>
