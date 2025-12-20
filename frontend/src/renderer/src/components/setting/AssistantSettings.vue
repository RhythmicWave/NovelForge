<script setup lang="ts">
import { computed } from 'vue'
import { useAssistantPreferences } from '@renderer/composables/useAssistantPreferences'

// 通过组合式统一管理灵感助手偏好，方便在设置页与助手面板之间复用
const prefs = useAssistantPreferences()

const ctxSummaryEnabled = computed({
  get: () => prefs.contextSummaryEnabled.value,
  set: (val: boolean) => prefs.setContextSummaryEnabled(val)
})

const ctxSummaryThreshold = computed({
  get: () => prefs.contextSummaryThreshold.value,
  set: (val: number | null) => prefs.setContextSummaryThreshold(val)
})

const reactModeEnabled = computed({
  get: () => prefs.reactModeEnabled.value,
  set: (val: boolean) => prefs.setReactModeEnabled(val)
})
</script>

<template>
  <div class="assistant-settings-root">
    <h3 class="section-title">灵感助手</h3>
    <p class="section-desc">
      配置灵感助手的高级能力，目前仅开放 React 工具解析协议。上下文摘要功能尚未启用。
    </p>

    <el-form label-width="140px" class="assistant-form" size="small">
      <el-form-item label="React 模式">
        <el-switch v-model="reactModeEnabled" />
      </el-form-item>
      <div class="field-hint">
        React 模式要求模型按照通过文本协议输出工具调用，
        系统会解析 Action 并真正调用工具，适合不支持函数调用的模型。
      </div>
    </el-form>
  </div>
</template>

<style scoped>
.assistant-settings-root {
  padding: 16px 12px 24px 12px;
}

.section-title {
  margin: 0 0 4px 0;
  font-size: 15px;
  font-weight: 600;
}

.section-desc {
  margin: 0 0 16px 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.assistant-form {
  max-width: 520px;
}

.field-hint {
  margin-left: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.hint-alert {
  margin-top: 12px;
}
</style>
