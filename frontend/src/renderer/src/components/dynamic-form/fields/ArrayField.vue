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
          v-if="isSimpleType"
          :is="getSimpleFieldComponent()"
          :label="`项目 ${index + 1}`"
          :prop="String(index)"
          :schema="itemSchema"
          :model-value="item"
          @update:modelValue="updateItem(index, $event)"
        />
        <!-- 对于复杂类型，使用ModelDrivenForm -->
        <ModelDrivenForm
          v-else
          :schema="itemSchema"
          :model-value="item"
          :display-name-map="displayNameMap"
          @update:model-value="updateItem(index, $event)"
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
function resolveActualSchema(schema: JSONSchema): JSONSchema {
  if (schema.$ref) {
    const refName = schema.$ref.split('/').pop() || ''
    const resolved = schemaService.getSchema(refName)
    if (resolved) {
      return { ...resolved, title: schema.title || resolved.title, description: schema.description || resolved.description };
    }
  }
  if (schema.anyOf) {
    const nonNullSchema = schema.anyOf.find(s => s.type !== 'null');
    if (nonNullSchema) {
      return resolveActualSchema({ ...nonNullSchema, title: schema.title, description: schema.description });
    }
  }
  return schema;
}

const itemSchema = computed((): JSONSchema => {
  if (props.schema.items) {
    return resolveActualSchema(props.schema.items)
  }
  return { type: 'string', title: '项目' }
})

// 判断是否为简单类型
const isSimpleType = computed(() => {
  const actualSchema = resolveActualSchema(itemSchema.value)
  return actualSchema.type === 'string' || actualSchema.type === 'number' || actualSchema.type === 'integer'
})

// 获取简单类型对应的字段组件
function getSimpleFieldComponent() {
  const actualSchema = resolveActualSchema(itemSchema.value)
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
  const defaultValue = createArrayItemDefaultValue(itemSchema.value)
  newArray.push(defaultValue)
  emit('update:modelValue', newArray)
}

/**
 * 智能地为任何 schema 创建一个有效的默认值，能够处理嵌套对象。
 */
function createDefaultValue(schema: JSONSchema): any {
  const actualSchema = resolveActualSchema(schema)

  if (actualSchema.default) {
    return actualSchema.default
  }
  if (actualSchema.enum && actualSchema.enum.length > 0) {
    return actualSchema.enum[0];
  }

  switch (actualSchema.type) {
    case 'object': {
      const obj: { [key: string]: any } = {}
      if (actualSchema.properties) {
        for (const key in actualSchema.properties) {
          obj[key] = createDefaultValue(actualSchema.properties[key])
        }
      }
      return obj
    }
    case 'array':
      if (actualSchema.prefixItems) {
        return actualSchema.prefixItems.map(item => createDefaultValue(item));
      }
      return []
    case 'string':
      return ''
    case 'number':
    case 'integer':
      return 0
    case 'boolean':
      return false
    default:
      return null
  }
}

/**
 * 为数组项创建默认值，确保与ModelDrivenForm兼容
 */
function createArrayItemDefaultValue(schema: JSONSchema): any {
  const actualSchema = resolveActualSchema(schema)
  
  // 如果是对象类型，需要创建完整的对象结构
  if (actualSchema.type === 'object') {
    const obj: { [key:string]: any } = {}
    if (actualSchema.properties) {
      for (const key in actualSchema.properties) {
        obj[key] = createDefaultValue(actualSchema.properties[key])
      }
    }
    return obj
  }
  
  // 对于其他类型，直接使用createDefaultValue
  return createDefaultValue(actualSchema)
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