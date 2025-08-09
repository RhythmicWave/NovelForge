<template>
  <div v-if="schema && modelValue !== undefined && typeof modelValue === 'object'" class="model-driven-form">
    <el-card shadow="never" class="form-card">
      <el-form :model="modelValue" label-position="top">
        <template v-for="(propSchema, propName) in visibleProperties" :key="propName">
          <component
            :is="getFieldComponent(propSchema)"
            :label="(displayNameMap && displayNameMap[propName]) || propSchema.title || String(propName)"
            :prop="String(propName)"
            :schema="resolveActualSchema(propSchema)"
            :display-name-map="displayNameMap"
            :model-value="modelValue[propName]"
            :readonly="readonlyFields.includes(String(propName))"
            :contextData="modelValue"
            :owner-id="ownerId"
            @update:modelValue="updateModel(String(propName), $event)"
          />
        </template>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { defineAsyncComponent, computed } from 'vue'
import type { JSONSchema } from '@renderer/api/schema'
import { schemaService } from '@renderer/api/schema'

// --- 组件导入 ---
const StringField = defineAsyncComponent(() => import('./fields/StringField.vue'))
const NumberField = defineAsyncComponent(() => import('./fields/NumberField.vue'))
const ObjectField = defineAsyncComponent(() => import('./fields/ObjectField.vue'))
const ArrayField = defineAsyncComponent(() => import('./fields/ArrayField.vue'))
const EnumField = defineAsyncComponent(() => import('./fields/EnumField.vue'))
const TupleField = defineAsyncComponent(() => import('./fields/TupleField.vue'))
// 用于不支持类型的默认回退组件
const FallbackField = defineAsyncComponent(() => import('./fields/FallbackField.vue'))

// --- Props & Emits ---
const props = defineProps<{
  schema: JSONSchema | undefined
  modelValue: Record<string, any>
  displayNameMap?: Record<string, string>
  readonlyFields?: string[]
  contextData?: Record<string, any>
  ownerId?: number | null
  includeFields?: string[]
  excludeFields?: string[]
}>()

const emit = defineEmits(['update:modelValue'])

// --- 默认值 ---
const readonlyFields = props.readonlyFields || []

const visibleProperties = computed(() => {
  const all = (props.schema?.properties || {}) as Record<string, JSONSchema>
  const entries = Object.entries(all)
  const included = props.includeFields && props.includeFields.length > 0
    ? entries.filter(([k]) => props.includeFields!.includes(k))
    : entries
  const excluded = props.excludeFields && props.excludeFields.length > 0
    ? included.filter(([k]) => !props.excludeFields!.includes(k))
    : included
  return Object.fromEntries(excluded)
})

// --- 逻辑 ---
function resolveActualSchema(schema: JSONSchema): JSONSchema {
  if (schema.anyOf) {
    const nonNullSchema = schema.anyOf.find(s => {
      if (s.type === 'null') return false
      if (s.$ref) return true
      if (s.type) return true
      return false
    });
    if (nonNullSchema) {
      if (nonNullSchema.$ref) {
        const refName = nonNullSchema.$ref.split('/').pop() || ''
        const resolvedSchema = schemaService.getSchema(refName)
        if (resolvedSchema) {
          return { ...resolvedSchema, title: schema.title, description: schema.description }
        }
      }
      return { ...nonNullSchema, title: schema.title, description: schema.description };
    }
  }
  if (schema.$ref) {
    const refName = schema.$ref.split('/').pop() || ''
    const resolvedSchema = schemaService.getSchema(refName)
    if (resolvedSchema) {
      return { ...resolvedSchema, title: schema.title, description: schema.description }
    }
  }
  return schema;
}

function getFieldComponent(propSchema: JSONSchema) {
  const actualSchema = resolveActualSchema(propSchema);
  if (actualSchema.enum && actualSchema.enum.length > 0) {
    return EnumField
  }
  if (actualSchema.type === 'array' && (actualSchema.prefixItems || actualSchema.anyOf)) {
    if (actualSchema.anyOf && !actualSchema.prefixItems) {
       return TupleField
    }
    if(actualSchema.prefixItems){
      return TupleField
    }
  }
  switch (actualSchema.type) {
    case 'string':
      return StringField
    case 'number':
    case 'integer':
      return NumberField
    case 'object':
      return ObjectField
    case 'array':
      return ArrayField
    default:
      console.warn(`不支持的字段类型: ${actualSchema.type} (属性: ${actualSchema.title}). 已使用回退组件。`)
      return FallbackField
  }
}

function updateModel(propName: string, value: any) {
  const newModel = { ...props.modelValue, [propName]: value }
  emit('update:modelValue', newModel)
}
</script>

<style scoped>
.model-driven-form { padding: 0; }
.form-card { border: none; }
:deep(.el-card__body) { padding: 20px; }
</style> 