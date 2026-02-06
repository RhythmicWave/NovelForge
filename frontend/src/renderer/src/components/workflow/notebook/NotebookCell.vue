<template>
  <div class="notebook-cell" :class="cellStatusClass">
    <div class="cell-header">
      <div class="cell-info">
        <span class="cell-variable">{{ cell.id }}</span>
        <el-tag :type="statusTagType" size="small">{{ statusText }}</el-tag>
      </div>
      <div class="cell-progress" v-if="cell.status === 'progress'">
        <el-progress
          :percentage="cell.progress || 0"
          :format="() => cell.message || '处理中...'"
          :stroke-width="6"
        />
      </div>
    </div>

    <div class="cell-content">
      <div class="cell-code">
        <pre><code>{{ cell.content }}</code></pre>
      </div>

      <div class="cell-output" v-if="hasOutput">
        <!-- 成功输出 -->
        <div v-if="cell.status === 'completed'" class="output-success">
          <div class="output-header">
            <el-icon><SuccessFilled /></el-icon>
            <span>执行成功</span>
          </div>
          <div class="output-content">
            <pre>{{ formatOutput(cell.outputs) }}</pre>
          </div>
        </div>

        <!-- 错误输出 -->
        <div v-if="cell.status === 'error'" class="output-error">
          <div class="output-header">
            <el-icon><CircleCloseFilled /></el-icon>
            <span>执行失败</span>
          </div>
          <div class="output-content">
            <pre>{{ cell.error }}</pre>
          </div>
        </div>

        <!-- 进度信息 -->
        <div v-if="cell.status === 'progress'" class="output-progress">
          <el-icon class="is-loading"><Loading /></el-icon>
          <span>{{ cell.message || '处理中...' }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, watch } from 'vue'
import { SuccessFilled, CircleCloseFilled, Loading } from '@element-plus/icons-vue'

const props = defineProps({
  cell: {
    type: Object,
    required: true
  }
})

const emit = defineEmits(['output'])

// 单元格状态样式类
const cellStatusClass = computed(() => {
  return `cell-status-${props.cell.status}`
})

// 状态标签类型
const statusTagType = computed(() => {
  const typeMap = {
    running: 'info',
    progress: 'warning',
    completed: 'success',
    error: 'danger'
  }
  return typeMap[props.cell.status] || 'info'
})

// 状态文本
const statusText = computed(() => {
  const textMap = {
    running: '运行中',
    progress: '处理中',
    completed: '已完成',
    error: '失败'
  }
  return textMap[props.cell.status] || '未知'
})

// 是否有输出
const hasOutput = computed(() => {
  return props.cell.status === 'completed' ||
         props.cell.status === 'error' ||
         props.cell.status === 'progress'
})

// 格式化输出
const formatOutput = (outputs) => {
  if (!outputs || outputs.length === 0) return ''

  const output = outputs[0]
  if (typeof output === 'object') {
    return JSON.stringify(output, null, 2)
  }
  return String(output)
}
</script>

<style scoped>
.notebook-cell {
  margin-bottom: 16px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  background: var(--el-bg-color);
  transition: all 0.3s;
}

.notebook-cell:hover {
  box-shadow: 0 2px 8px var(--el-box-shadow-light);
}

.cell-status-running {
  border-left: 3px solid var(--el-color-primary);
}

.cell-status-progress {
  border-left: 3px solid var(--el-color-warning);
}

.cell-status-completed {
  border-left: 3px solid var(--el-color-success);
}

.cell-status-error {
  border-left: 3px solid var(--el-color-danger);
}

.cell-header {
  padding: 12px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background: var(--el-fill-color-lighter);
}

.cell-info {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.cell-variable {
  font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.cell-progress {
  margin-top: 8px;
}

.cell-content {
  padding: 16px;
}

.cell-code {
  margin-bottom: 12px;
}

.cell-code pre {
  margin: 0;
  padding: 12px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.6;
  color: var(--el-text-color-primary);
  overflow-x: auto;
}

.cell-code code {
  font-family: inherit;
}

.cell-output {
  margin-top: 12px;
}

.output-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
  font-size: 14px;
  font-weight: 600;
}

.output-success .output-header {
  color: var(--el-color-success);
}

.output-error .output-header {
  color: var(--el-color-danger);
}

.output-progress {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  background: var(--el-color-primary-light-9);
  border-radius: 4px;
  color: var(--el-color-primary);
}

.output-content {
  padding: 12px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  max-height: 400px;
  overflow-y: auto;
}

.output-content pre {
  margin: 0;
  font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.6;
  color: var(--el-text-color-primary);
  white-space: pre-wrap;
  word-wrap: break-word;
}

.output-error .output-content {
  background: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
}
</style>