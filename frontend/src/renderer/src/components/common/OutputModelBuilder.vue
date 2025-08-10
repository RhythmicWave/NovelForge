<template>
  <div class="schema-builder">
    <div class="toolbar">
      <el-button type="primary" @click="addField">新增字段</el-button>
    </div>
    <el-table :data="localFields" size="small" class="field-table">
      <el-table-column label="名称" width="150">
        <template #default="{ row }">
          <el-input v-model="row.name" placeholder="字段名" />
        </template>
      </el-table-column>
      <el-table-column label="显示名" width="150">
        <template #default="{ row }">
          <el-input v-model="row.label" placeholder="用于表单显示的标题" />
        </template>
      </el-table-column>
      <el-table-column label="类型" width="150">
        <template #default="{ row }">
          <el-select v-model="row.kind" @change="onKindChange(row)">
            <el-option v-for="t in baseKinds" :key="t" :label="t" :value="t" />
            <el-option label="relation(embed)" value="relation" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="数组" width="80" align="center">
        <template #default="{ row }">
          <el-switch v-model="row.isArray" />
        </template>
      </el-table-column>
      <el-table-column label="必填" width="80" align="center">
        <template #default="{ row }">
          <el-switch v-model="row.required" />
        </template>
      </el-table-column>
      <el-table-column label="注解" min-width="240">
        <template #default="{ row }">
          <el-input v-model="row.description" placeholder="用于 Field 描述，提升 AI 结构化准确率" />
        </template>
      </el-table-column>
      <el-table-column label="关系配置" min-width="200">
        <template #default="{ row }">
          <div v-if="row.kind==='relation'" class="rel-config">
            <el-select v-model="row.relation.targetModelName" filterable placeholder="选择目标输出模型" style="width:260px">
              <el-option v-for="t in targetModels" :key="t.name" :label="t.name" :value="t.name" :disabled="isEmbedSelf(row, t.name)" />
            </el-select>
          </div>
          <div v-else class="rel-config muted">—</div>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150" align="right">
        <template #default="{ $index }">
          <el-button size="small" @click="moveUp($index)" :disabled="$index===0">上移</el-button>
          <el-button size="small" @click="moveDown($index)" :disabled="$index===localFields.length-1">下移</el-button>
          <el-button size="small" type="danger" plain @click="removeField($index)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed, nextTick } from 'vue'

export interface OutputModelLite { name: string; json_schema?: any }

export interface BuilderField {
  name: string
  label?: string
  kind: 'string' | 'number' | 'integer' | 'boolean' | 'relation'
  isArray?: boolean
  required?: boolean
  relation: { targetModelName: string | null }
  description?: string
}

const props = defineProps<{
  modelValue: BuilderField[]
  // 所有可用的输出模型（用于 embed）
  models: OutputModelLite[]
  // 当前正在编辑的模型名称（避免自嵌）
  currentModelName?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: BuilderField[]] }>()

const baseKinds: Array<BuilderField['kind']> = ['string', 'number', 'integer', 'boolean']

const localFields = ref<BuilderField[]>(props.modelValue?.map(cloneField) || [])
const syncingFromProps = ref(false)
watch(() => props.modelValue, async (v) => {
  syncingFromProps.value = true
  localFields.value = (v || []).map(cloneField)
  await nextTick()
  syncingFromProps.value = false
})
watch(localFields, (v) => { if (!syncingFromProps.value) emit('update:modelValue', v) }, { deep: true })

const targetModels = computed(() => props.models || [])

function cloneField(f: BuilderField): BuilderField {
  return JSON.parse(JSON.stringify(f))
}

function addField() {
  localFields.value.push({ name: '', label: '', kind: 'string', isArray: false, required: false, relation: { targetModelName: null }, description: '' })
}
function removeField(idx: number) { localFields.value.splice(idx, 1) }
function moveUp(idx: number) { if (idx <= 0) return; const a = localFields.value; [a[idx-1], a[idx]] = [a[idx], a[idx-1]] }
function moveDown(idx: number) { const a = localFields.value; if (idx >= a.length - 1) return; [a[idx+1], a[idx]] = [a[idx], a[idx+1]] }
function onKindChange(row: BuilderField) {
  if (row.kind !== 'relation') row.relation = { targetModelName: null }
}
function isEmbedSelf(row: BuilderField, targetName: string) {
  return row.kind === 'relation' && props.currentModelName && props.currentModelName === targetName
}

function builderToSchema(fields: BuilderField[]): any {
  const properties: Record<string, any> = {}
  const required: string[] = []
  const defs: Record<string, any> = {}
  for (const f of fields) {
    if (!f.name) continue
    const title = f.label || f.name
    let node: any = {}
    if (f.kind === 'relation') {
      const defName = f.relation.targetModelName
      if (defName) {
        node = f.isArray ? { type: 'array', items: { $ref: `#/$defs/${defName}` } } : { $ref: `#/$defs/${defName}` }
        const target = targetModels.value.find(m => m.name === defName)
        if (target?.json_schema) defs[defName] = target.json_schema
      } else {
        node = { type: 'object', properties: {} }
      }
    } else {
      node = { type: f.kind }
      if (f.isArray) node = { type: 'array', items: node }
    }
    node.title = title
    if (f.description) node.description = f.description
    properties[f.name] = node
    if (f.required) required.push(f.name)
  }
  const schema: any = { type: 'object', properties }
  if (required.length) schema.required = required
  if (Object.keys(defs).length) schema.$defs = defs
  return schema
}

function schemaToBuilder(schema: any): BuilderField[] {
  const props = schema?.properties || {}
  const required: string[] = schema?.required || []
  const fields: BuilderField[] = []
  for (const key of Object.keys(props)) {
    const p = props[key]
    const isArray = p?.type === 'array'
    const core = isArray ? p.items : p
    let kind: BuilderField['kind'] = 'string'
    let relation: BuilderField['relation'] = { targetModelName: null }
    if (core?.$ref) {
      kind = 'relation'
      const refName = String(core.$ref).split('/').pop() || null
      relation = { targetModelName: refName }
    } else if (core?.type && ['string','number','integer','boolean'].includes(core.type)) {
      kind = core.type
    }
    fields.push({ name: key, label: core?.title || key, kind, isArray, required: required.includes(key), relation, description: core?.description || p?.description || '' })
  }
  return fields
}
</script>

<style scoped>
.schema-builder { display: flex; flex-direction: column; gap: 8px; }
.toolbar { display: flex; gap: 8px; }
.field-table { width: 100%; }
.rel-config { display: flex; gap: 8px; align-items: center; }
.muted { color: var(--el-text-color-secondary); }
</style> 