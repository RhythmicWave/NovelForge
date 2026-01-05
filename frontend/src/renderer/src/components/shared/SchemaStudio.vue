<template>
  <el-dialog
    :model-value="visible"
    @update:model-value="(v:boolean) => emit('update:visible', v)"
    :title="headerTitle"
    width="92%"
    top="4vh"
  >
    <div class="studio">
      <div class="left">
        <template v-if="mode==='type'">
          <el-form label-position="top" class="modelname-form">
            <el-form-item label="模型名称">
              <el-input v-model="modelName" placeholder="不填则默认等于卡片类型名" />
            </el-form-item>
          </el-form>
        </template>
        <div class="pane-header">结构构建器</div>
        <OutputModelBuilder v-model="builderFields" :models="relationTargets" :current-model-name="contextTitle" />
      </div>
      <div class="right">
        <div class="subpane">
          <div class="pane-header">表单预览</div>
          <div class="preview">
            <ModelDrivenForm v-if="schemaObject" :schema="schemaObject" v-model="previewModel" />
            <div v-else class="placeholder">暂无 Schema</div>
          </div>
        </div>
        <div class="subpane">
          <div class="pane-header">Schema JSON</div>
          <el-input type="textarea" :rows="12" :model-value="schemaText" readonly />
        </div>
      </div>
    </div>
    <template #footer>
      <div class="footer-actions">
        <el-button @click="emit('update:visible', false)">关闭</el-button>
        <template v-if="mode==='card'">
          <el-button @click="restoreFollowType" type="warning" plain>恢复跟随类型</el-button>
          <el-button @click="applyToType" type="primary" plain>应用到类型</el-button>
          <el-button @click="saveForCard" type="primary">仅此卡生效</el-button>
        </template>
        <template v-else>
          <el-button type="primary" @click="saveForType">保存到类型</el-button>
        </template>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, onBeforeUnmount, watch } from 'vue'
import OutputModelBuilder from '../setting/OutputModelBuilder.vue'
import ModelDrivenForm from '../dynamic-form/ModelDrivenForm.vue'
import { schemaToBuilder, builderToSchema, type BuilderField } from '@renderer/utils/outputModelSchemaUtils'
import { ElMessage } from 'element-plus'
import { getCardTypeSchema, updateCardTypeSchema, getCardSchema, updateCardSchema, applyCardSchemaToType, listCardTypes, updateCardType } from '@renderer/api/setting'

const props = defineProps<{ visible: boolean; mode: 'type' | 'card'; targetId: number; contextTitle?: string }>()
const emit = defineEmits<{ 'update:visible': [boolean]; 'saved': []; 'close': [] }>()

const headerTitle = computed(() => props.mode === 'type' ? `类型结构编辑：${props.contextTitle || props.targetId}` : `实例结构编辑：${props.contextTitle || props.targetId}`)

const builderFields = ref<BuilderField[]>([])
const relationTargets = ref<Array<{ name: string; json_schema?: any }>>([])
const previewModel = ref<any>({})
const modelName = ref<string>('')
// 保留原始 schema，用于保护复杂字段（如 dynamic_info）的结构不被简化覆盖
const originalSchema = ref<any | null>(null)

const schemaObject = computed(() => {
  try {
    const base: any = builderToSchema(builderFields.value) as any

    // 若原始 schema 中存在复杂对象字段（目前主要是 dynamic_info），
    // 为避免被简化的 builder 覆盖其结构，这里用原始定义进行回填。
    const orig = originalSchema.value as any
    if (orig && typeof orig === 'object' && orig.properties && base && base.properties) {
      const origProps = orig.properties as Record<string, any>
      const nextProps = { ...(base.properties as Record<string, any>) }
      if (origProps.dynamic_info && Object.prototype.hasOwnProperty.call(nextProps, 'dynamic_info')) {
        nextProps.dynamic_info = origProps.dynamic_info
        base.properties = nextProps
      }
    }

    const defs: Record<string, any> = {}
    // 收集被引用的目标模型结构
    for (const f of builderFields.value) {
      if (f.kind === 'relation' && f.relation?.targetModelName) {
        const name = f.relation.targetModelName
        const found = relationTargets.value.find(m => m.name === name)
        if (found?.json_schema) defs[name] = found.json_schema
      }
    }
    // 若类型模式且设置了模型名，可作为当前模型名称引用（供外部使用）
    if (Object.keys(defs).length) base.$defs = defs
    return base
  } catch { return null }
})
const schemaText = computed(() => {
  try { return JSON.stringify(schemaObject.value || {}, null, 2) } catch { return '' }
})

async function loadSchema() {
  if (!props.visible) return
  if (!props.targetId || props.targetId <= 0) return
  try {
    if (props.mode === 'type') {
      const resp = await getCardTypeSchema(props.targetId)
      const sch = (resp?.json_schema || {})
      originalSchema.value = sch
      builderFields.value = schemaToBuilder(sch)
    } else {
      const resp = await getCardSchema(props.targetId)
      const sch = (resp?.effective_schema || resp?.json_schema || {})
      originalSchema.value = sch
      builderFields.value = schemaToBuilder(sch)
    }

    // 载入可被引用的目标模型（所有卡片类型）
    try {
      const types = await listCardTypes()
      const list = (types || []) as any[]
      relationTargets.value = list.filter(t => !!t.json_schema).map(t => ({ name: t.model_name || t.name, json_schema: t.json_schema }))
      if (props.mode === 'type') {
        const me = list.find(t => t.id === props.targetId)
        modelName.value = me?.model_name || ''
      }
    } catch {}
  } catch (e:any) {
    ElMessage.error('加载 Schema 失败')
  }
}

async function saveForType() {
  try {
    // 先保存模型名（如有修改）
    if (props.mode === 'type') {
      await updateCardType(props.targetId, { model_name: modelName.value || null } as any)
    }
    await updateCardTypeSchema(props.targetId, schemaObject.value || {})
    ElMessage.success('已保存到类型结构')
    emit('saved')
  } catch (e:any) { ElMessage.error('保存失败') }
}

async function saveForCard() {
  try {
    await updateCardSchema(props.targetId, schemaObject.value || {})
    ElMessage.success('已保存，仅此卡生效')
    emit('saved')
  } catch (e:any) { ElMessage.error('保存失败') }
}

async function restoreFollowType() {
  try {
    await updateCardSchema(props.targetId, null)
    ElMessage.success('已恢复跟随类型')
    await loadSchema()
    emit('saved')
  } catch (e:any) { ElMessage.error('操作失败') }
}

async function applyToType() {
  try {
    await applyCardSchemaToType(props.targetId)
    ElMessage.success('已应用到类型')
    emit('saved')
  } catch (e:any) { ElMessage.error('应用失败') }
}

function handleKey(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
    e.preventDefault()
    if (props.mode === 'type') saveForType()
    else saveForCard()
  }
}

watch(() => props.visible, (v) => { if (v) loadSchema() }, { immediate: false })
watch(() => props.targetId, () => { if (props.visible) loadSchema() })

onBeforeUnmount(() => { window.removeEventListener('keydown', handleKey) })

const contextTitle = computed(() => props.contextTitle || '')
</script>

<style scoped>
.studio { display: grid; grid-template-columns: 1.2fr 1fr; gap: 12px; height: 72vh; }
.left { display: flex; flex-direction: column; gap: 8px; overflow: auto; }
.right { display: grid; grid-template-rows: 1fr 1fr; gap: 8px; overflow: auto; }
.subpane { display: flex; flex-direction: column; overflow: auto; }
.pane-header { font-weight: 600; margin-bottom: 6px; }
.preview { flex: 1; overflow: auto; border: 1px solid var(--el-border-color-light); padding: 8px; border-radius: 6px; }
.footer-actions { display: flex; gap: 8px; justify-content: flex-end; width: 100%; }
.placeholder { color: var(--el-text-color-secondary); padding: 12px; }
.modelname-form { padding: 6px 0; }
/* 与窗口按钮保持距离 */
:deep(.el-dialog__headerbtn) { margin-right: 6px; }
</style> 