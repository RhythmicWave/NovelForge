<template>
  <div class="code-workflow-editor-view">
    <Workflow />
  </div>
</template>

<script setup>
import Workflow from '@/components/workflow/Workflow.vue'
</script>

<style scoped>
.code-workflow-editor-view {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
}
</style>
