<script setup lang="ts">
import { onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useProjectStore } from '@renderer/stores/useProjectStore'
import Editor from './Editor.vue'

const projectStore = useProjectStore()
const { currentProject } = storeToRefs(projectStore)

onMounted(async () => {
  // 若未加载或不是保留项目，则加载保留项目
  if (!currentProject.value || (currentProject.value.name || '') !== '__free__') {
    await projectStore.loadFreeProject()
  }
})
</script>

<template>
  <div class="ideas-home">
    <template v-if="currentProject">
      <Editor :initial-project="currentProject" />
    </template>
    <template v-else>
      <el-skeleton animated :rows="6" style="padding: 24px;" />
    </template>
  </div>
</template>

<style scoped>
.ideas-home { height: 100%; }
</style> 