<template>
  <el-card shadow="never" class="array-field-card">
    <template #header>
      <div class="card-header">
        <span>{{ label }}</span>
      </div>
    </template>

    <div v-if="!modelValue || modelValue.length === 0" class="empty-state">
      <p>暂无项目</p>
    </div>

    <div v-for="(item, index) in modelValue" :key="index" class="array-item">
      <div class="array-item-content">
        <!-- 对于简单类型，直接使用对应的字段组件 -->
        <component
          v-if="isSimpleTypeForIndex(index)"
          :is="getSimpleFieldComponentForIndex(index)"
          :label="`项目 ${index + 1}`"
          :prop="String(index)"
          :schema="getItemSchemaForIndex(index)"
          :model-value="item"
          @update:modelValue="updateItem(index, $event)"
        />
        <!-- 对于复杂类型，使用ModelDrivenForm -->
        <ModelDrivenForm
          v-else
          :schema="getItemSchemaForIndex(index)"
          :model-value="item"
          :display-name-map="displayNameMap"
          @update:modelValue="updateItem(index, $event)"
        />
      </div>
      <div class="array-item-actions">
        <el-button
          type="danger"
          :icon="Delete"
          circle
          plain
          size="small"
          @click="removeItem(index)"
        />
      </div>
    </div>
    <el-button type="primary" :icon="Plus" plain @click="addItem" class="add-button">
      添加 {{ (displayNameMap && displayNameMap[itemSchema.title || '']) || itemSchema.title || '新项目' }}
    </el-button>
  </el-card>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue'
import { schemaService, type JSONSchema } from '@renderer/api/schema'
import { Delete, Plus } from '@element-plus/icons-vue'
import { resolveActualSchema } from '@renderer/services/schemaFieldParser'

const ModelDrivenForm = defineAsyncComponent(() => import('../ModelDrivenForm.vue'))
const StringField = defineAsyncComponent(() => import('./StringField.vue'))
const NumberField = defineAsyncComponent(() => import('./NumberField.vue'))

const props = defineProps<{
  modelValue: any[] | undefined
  label: string
  schema: JSONSchema
  displayNameMap?: Record<string, string>
  readonly?: boolean
  contextData?: Record<string, any>
  ownerId?: number | null // 接收最外层传来的ID
}>()

const emit = defineEmits(['update:modelValue'])


/**
 * 递归地解析 schema，处理 $ref 和 anyOf (Optional)
 */
// 移除重复的resolveActualSchema函数，使用公共服务

const itemSchema = computed((): JSONSchema => {
  if (props.schema.items) {
    return resolveActualSchema(props.schema.items, props.schema)
  }
  return { type: 'string', title: '项目' }
})

function getItemSchemaForIndex(index: number): JSONSchema {
  const base = itemSchema.value
  const value = (props.modelValue || [])[index]
  if ((base as any).anyOf) {
    const matched = resolveAnyOfForValue(base, value)
    if (matched) return matched
  }
  return base
}

// 判断是否为简单类型（按索引）
function isSimpleTypeForIndex(index: number) {
  const actualSchema = getItemSchemaForIndex(index)
  return actualSchema.type === 'string' || actualSchema.type === 'number' || actualSchema.type === 'integer'
}

// 获取简单类型对应的字段组件（按索引）
function getSimpleFieldComponentForIndex(index: number) {
  const actualSchema = getItemSchemaForIndex(index)
  switch (actualSchema.type) {
    case 'string':
      return StringField
    case 'number':
    case 'integer':
      return NumberField
    default:
      return StringField
  }
}

function updateItem(index: number, newItem: any) {
  const newArray = [...(props.modelValue || [])]
  newArray[index] = newItem
  emit('update:modelValue', newArray)
}

function removeItem(index: number) {
  const newArray = [...(props.modelValue || [])]
  newArray.splice(index, 1)
  emit('update:modelValue', newArray)
}

function addItem() {
  const newArray = [...(props.modelValue || [])]
  const base = itemSchema.value
  let defaultValue: any

  if ((base as any).anyOf) {
    // 默认新增为 character，可在 UI 改 entity_type 触发切换
    defaultValue = { name: '', entity_type: 'character', life_span: '短期' }
  } else {
    defaultValue = createArrayItemDefaultValue(base)
  }

  newArray.push(defaultValue)
  emit('update:modelValue', newArray)
}

/**
 * 智能地为任何 schema 创建一个有效的默认值，能够处理嵌套对象。
 */
// 移除重复的createDefaultValue函数，使用公共服务

/**
 * 为数组项创建默认值，确保与ModelDrivenForm兼容
 */
function createArrayItemDefaultValue(schema: JSONSchema): any {
  const actualSchema = resolveActualSchema(schema, props.schema)
  
  if (actualSchema.default !== undefined) {
    return actualSchema.default
  }
  
  switch (actualSchema.type) {
    case 'string': return ''
    case 'number':
    case 'integer': return 0
    case 'boolean': return false
    case 'array': return []
    case 'object': return {}
    default: return null
  }
}

function resolveAnyOfForValue(base: JSONSchema, value: any): JSONSchema | null {
  if (!base.anyOf) return null
  
  // 简单实现：找到第一个非null的Schema
  const nonNullSchema = base.anyOf.find((s: any) => s && s.type !== 'null')
  return nonNullSchema ? resolveActualSchema(nonNullSchema as JSONSchema, props.schema) : null
}
</script>

<style scoped>
.array-field-card {
  margin-top: 10px;
  margin-bottom: 20px;
  background-color: var(--el-fill-color-lighter);
}
.empty-state {
  text-align: center;
  color: var(--el-text-color-secondary);
  padding: 20px 0;
}
.array-item {
  display: flex;
  align-items: flex-start;
  margin-bottom: 15px;
  padding: 15px;
  border: 1px dashed var(--el-border-color);
  border-radius: 4px;
}
.array-item-content {
  flex-grow: 1;
  padding-right: 15px;
}
.array-item-actions {
  flex-shrink: 0;
}
.add-button {
  margin-top: 10px;
  width: 100%;
}
</style> 