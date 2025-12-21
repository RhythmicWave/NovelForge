<script setup lang="ts">
import { computed } from 'vue'
import { QuestionFilled } from '@element-plus/icons-vue'
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

const assistantTemperature = computed({
  get: () => prefs.assistantTemperature.value,
  set: (val: number | null) => prefs.setAssistantTemperature(val)
})

const assistantMaxTokens = computed({
  get: () => prefs.assistantMaxTokens.value,
  set: (val: number | null) => prefs.setAssistantMaxTokens(val)
})

const assistantTimeout = computed({
  get: () => prefs.assistantTimeout.value,
  set: (val: number | null) => prefs.setAssistantTimeout(val)
})
</script>

<template>
  <div class="assistant-settings-root">
    <h3 class="section-title">灵感助手</h3>
    <p class="section-desc">
      配置灵感助手的高级能力，目前仅开放 React 工具解析协议。上下文摘要功能尚未启用。
    </p>

    <el-form label-width="160px" class="assistant-form" size="small">
      <!-- 参数配置组 -->
      <div class="group-title">参数设置</div>

      <el-form-item>
        <template #label>
          <span>
            采样温度 (temperature)
            <el-tooltip placement="top" effect="dark">
              <template #content>
                控制输出的随机性，数值越大越有创意、越发散，越小越保守、越稳定。<br/>
                建议范围 0.4 ~ 0.9。默认值为 0.6。
              </template>
              <el-icon class="field-help-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </span>
        </template>
        <el-input-number
          v-model="assistantTemperature"
          :min="0.1"
          :max="2"
          :step="0.1"
          :precision="2"
          controls-position="right"
          placeholder="0.6"
        />
      </el-form-item>

      <el-form-item>
        <template #label>
          <span>
            最大输出 Token 数
            <el-tooltip placement="top" effect="dark">
              <template #content>
                控制单次回复的最大长度。值越大，回复可以越长，但也会增加响应时间和费用。<br/>
                默认值为 8192。
              </template>
              <el-icon class="field-help-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </span>
        </template>
        <el-input-number
          v-model="assistantMaxTokens"
          :min="256"
          :max="65536"
          :step="512"
          controls-position="right"
          placeholder="8192"
        />
      </el-form-item>

      <el-form-item>
        <template #label>
          <span>
            超时 (秒)
            <el-tooltip placement="top" effect="dark">
              <template #content>
                限制单次调用的最长等待时间，避免请求长时间挂起。<br/>
                默认值为 90 秒。
              </template>
              <el-icon class="field-help-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </span>
        </template>
        <el-input-number
          v-model="assistantTimeout"
          :min="10"
          :max="600"
          :step="10"
          controls-position="right"
          placeholder="90"
        />
      </el-form-item>

      <el-divider />

      <!-- React 配置组 -->
      <div class="group-title">模式设置</div>
      <el-form-item>
        <template #label>
          <span>
            React 模式
            <el-tooltip placement="top" effect="dark">
              <template #content>
                让模型通过文本协议输出工具调用指令（<Action>{...}</Action>），
                系统解析后真正调用工具，适合不支持函数调用的模型。
              </template>
              <el-icon class="field-help-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </span>
        </template>
        <el-switch v-model="reactModeEnabled" />
      </el-form-item>
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

.group-title {
  margin: 8px 0 4px 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-regular);
}

.field-help-icon {
  margin-left: 4px;
  cursor: help;
}
</style>
