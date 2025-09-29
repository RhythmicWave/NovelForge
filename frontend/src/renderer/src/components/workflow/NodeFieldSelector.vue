<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { QuestionFilled, InfoFilled } from '@element-plus/icons-vue'

const props = defineProps<{
  fieldKey: string
  fieldValue: any
  fieldConfig: {
    type: 'select' | 'input' | 'textarea' | 'number' | 'switch'
    options?: Array<{ label: string; value: any; desc?: string }>
    placeholder?: string
    description?: string
    required?: boolean
    validator?: (value: any) => boolean | string
  }
  disabled?: boolean
}>()

const emit = defineEmits<{
  'update:value': [value: any]
}>()

// 本地值，用于实时编辑但延迟提交
const localValue = ref(formatValueForDisplay(props.fieldValue))

// 格式化值用于显示
function formatValueForDisplay(value: any): any {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    try {
      return JSON.stringify(value, null, 2)
    } catch {
      return String(value)
    }
  }
  return value
}

// 解析显示值为实际值
function parseDisplayValue(displayValue: any): any {
  if (typeof displayValue === 'string' && (displayValue.trim().startsWith('{') || displayValue.trim().startsWith('['))) {
    try {
      return JSON.parse(displayValue)
    } catch {
      return displayValue
    }
  }
  return displayValue
}

// 验证状态
const validationResult = computed(() => {
  if (!props.fieldConfig.validator) return { valid: true, message: '' }
  const result = props.fieldConfig.validator(localValue.value)
  if (typeof result === 'boolean') {
    return { valid: result, message: result ? '' : '值无效' }
  }
  return { valid: false, message: result }
})

// 监听外部值变化
watch(() => props.fieldValue, (newValue) => {
  localValue.value = formatValueForDisplay(newValue)
})

// 提交值的变化
const commitValue = () => {
  if (validationResult.value.valid) {
    const actualValue = parseDisplayValue(localValue.value)
    emit('update:value', actualValue)
  }
}

// 实时更新（适用于某些类型）
const handleInput = (value: any) => {
  localValue.value = value
  // 对于select、switch等类型，立即提交
  if (['select', 'switch'].includes(props.fieldConfig.type)) {
    const actualValue = parseDisplayValue(value)
    emit('update:value', actualValue)
  }
}
</script>

<template>
  <div class="node-field-selector" :class="{ 'field-invalid': !validationResult.valid }">
    <div class="field-header">
      <label class="field-label">
        {{ fieldKey }}
        <span v-if="fieldConfig.required" class="required-mark">*</span>
      </label>
      <el-tooltip 
        v-if="fieldConfig.description" 
        :content="fieldConfig.description"
        placement="top"
        :show-after="500"
      >
        <el-icon class="help-icon"><InfoFilled /></el-icon>
      </el-tooltip>
    </div>

    <div class="field-input">
      <!-- Select 类型 -->
      <template v-if="fieldConfig.type === 'select'">
        <el-select
          :model-value="localValue"
          :placeholder="fieldConfig.placeholder || `请选择${fieldKey}`"
          :disabled="disabled"
          style="width: 100%"
          clearable
          filterable
          @update:model-value="handleInput"
        >
          <el-option
            v-for="option in fieldConfig.options || []"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          >
            <div class="option-item">
              <span class="option-label">{{ option.label }}</span>
              <span v-if="option.desc" class="option-desc">{{ option.desc }}</span>
            </div>
          </el-option>
        </el-select>
      </template>

      <!-- Input 类型 -->
      <template v-else-if="fieldConfig.type === 'input'">
        <el-input
          v-model="localValue"
          :placeholder="fieldConfig.placeholder || `请输入${fieldKey}`"
          :disabled="disabled"
          @blur="commitValue"
          @keyup.enter="commitValue"
        />
      </template>

      <!-- Textarea 类型 -->
      <template v-else-if="fieldConfig.type === 'textarea'">
        <el-input
          v-model="localValue"
          type="textarea"
          :rows="3"
          :placeholder="fieldConfig.placeholder || `请输入${fieldKey}`"
          :disabled="disabled"
          @blur="commitValue"
        />
      </template>

      <!-- Number 类型 -->
      <template v-else-if="fieldConfig.type === 'number'">
        <el-input-number
          v-model="localValue"
          :placeholder="fieldConfig.placeholder"
          :disabled="disabled"
          style="width: 100%"
          @blur="commitValue"
          @change="commitValue"
        />
      </template>

      <!-- Switch 类型 -->
      <template v-else-if="fieldConfig.type === 'switch'">
        <el-switch
          v-model="localValue"
          :disabled="disabled"
          @change="handleInput"
        />
      </template>
    </div>

    <!-- 验证错误提示 -->
    <div v-if="!validationResult.valid" class="validation-error">
      <el-icon><QuestionFilled /></el-icon>
      <span>{{ validationResult.message }}</span>
    </div>
  </div>
</template>

<style scoped>
.node-field-selector {
  margin-bottom: 12px;
}

.field-header {
  display: flex;
  align-items: center;
  margin-bottom: 6px;
}

.field-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--el-text-color-regular);
  margin-right: 4px;
}

.required-mark {
  color: var(--el-color-danger);
  margin-left: 2px;
}

.help-icon {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  cursor: help;
}

.field-input {
  width: 100%;
}

.field-invalid .field-input {
  border-color: var(--el-color-danger);
}

.option-item {
  display: flex;
  flex-direction: column;
}

.option-label {
  font-size: 13px;
  color: var(--el-text-color-primary);
}

.option-desc {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin-top: 2px;
}

.validation-error {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 4px;
  font-size: 11px;
  color: var(--el-color-danger);
}

.validation-error .el-icon {
  font-size: 12px;
}

/* 自定义组件样式 */
:deep(.el-select) {
  width: 100%;
}

:deep(.el-input__wrapper) {
  font-size: 12px;
}

:deep(.el-textarea__inner) {
  font-size: 12px;
  resize: vertical;
}

:deep(.el-input-number) {
  width: 100% !important;
}

:deep(.el-input-number .el-input__wrapper) {
  padding-left: 8px;
  padding-right: 8px;
}
</style>
