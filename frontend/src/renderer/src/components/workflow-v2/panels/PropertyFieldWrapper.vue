<template>
  <div class="property-field-wrapper">
    <slot />
    <div v-if="showConnectionHint" class="connection-hint">
      <el-icon><Connection /></el-icon>
      已有连线提供默认值
    </div>
  </div>
</template>

<script setup lang="ts">
import { Connection } from '@element-plus/icons-vue'

defineProps<{
  showConnectionHint: boolean
}>()
</script>

<style scoped lang="scss">
.property-field-wrapper {
  width: 100%;
  position: relative;
}

.connection-hint {
  margin-top: 6px;
  padding: 4px 8px;
  background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%);
  color: #1976d2;
  border: 1px solid #90caf9;
  border-radius: 4px;
  font-size: 11px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-weight: 500;
  
  .el-icon {
    font-size: 12px;
    color: #1976d2;
  }
}
</style>
