<template>
  <div class="output-model-manager">
    <div class="header">
      <h4>输出模型管理</h4>
      <el-button type="primary" size="small" @click="openEditor()">新建模型</el-button>
    </div>

    <el-table :data="models" height="60vh" size="small" v-loading="loading">
      <el-table-column prop="name" label="名称" width="220" />
      <el-table-column prop="description" label="描述" min-width="260" />
      <el-table-column label="内置" width="90">
        <template #default="{ row }">
          <el-tag size="small" :type="row.built_in ? 'info' : 'success'">{{ row.built_in ? '内置' : '自定义' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="180" align="right">
        <template #default="{ row }">
          <el-button size="small" @click="openEditor(row)">编辑</el-button>
          <el-popconfirm title="删除该模型？" @confirm="remove(row)">
            <template #reference>
              <el-button size="small" type="danger" plain :disabled="row.built_in">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <el-drawer v-model="editor.visible" :title="editor.editing ? '编辑输出模型' : '新建输出模型'" size="85%">
      <div class="editor-grid">
        <el-form label-position="top">
          <el-form-item label="名称">
            <el-input v-model="editor.form.name" :disabled="editor.editing" />
          </el-form-item>
          <el-form-item label="描述">
            <el-input v-model="editor.form.description" type="textarea" :rows="2" />
          </el-form-item>
          <el-alert type="info" :closable="false" show-icon title="推荐使用可视化 Builder 定义字段结构；如需手动编写 JSON，可开启高级模式" />
          <div class="mode-toggle"><span>高级模式</span><el-switch v-model="advancedMode" /></div>
          <template v-if="!advancedMode">
            <OutputModelBuilder v-model="builderFields" :models="modelsLite" :current-model-name="editor.form.name || undefined" />
          </template>
          <template v-else>
            <el-form-item label="JSON Schema（高级模式）">
              <el-input v-model="schemaText" type="textarea" :rows="18" />
            </el-form-item>
          </template>
        </el-form>
      </div>
      <template #footer>
        <el-button @click="editor.visible=false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import OutputModelBuilder from './OutputModelBuilder.vue'
import { type BuilderField, schemaToBuilder as utilSchemaToBuilder, builderToSchema as utilBuilderToSchema } from '@renderer/utils/outputModelSchemaUtils'
import { listOutputModels, createOutputModel, updateOutputModel, deleteOutputModel, type OutputModel as OM } from '@renderer/api/setting'

interface OutputModel extends OM {}

const loading = ref(false)
const models = ref<OutputModel[]>([])
const modelsLite = computed(() => models.value.map(m => ({ name: m.name, json_schema: m.json_schema })))

const editor = reactive<{ visible: boolean; editing: boolean; form: OutputModel }>({
  visible: false,
  editing: false,
  form: { name: '', description: '', json_schema: {} }
})

const advancedMode = ref(false)
const schemaText = ref('')
const builderFields = ref<BuilderField[]>([])

async function fetchModels() {
  loading.value = true
  try { models.value = await listOutputModels() } finally { loading.value = false }
}

function openEditor(row?: OutputModel) {
  if (row) {
    editor.visible = true
    editor.editing = true
    editor.form = { ...row }
    schemaText.value = JSON.stringify(row.json_schema ?? {}, null, 2)
    builderFields.value = utilSchemaToBuilder(editor.form.json_schema as any)
    advancedMode.value = false
  } else {
    editor.visible = true
    editor.editing = false
    editor.form = { name: '', description: '', json_schema: {} }
    schemaText.value = '{\n  "type": "object",\n  "properties": {}\n}'
    builderFields.value = []
    advancedMode.value = false
  }
}

function builderToSchema(fields: BuilderField[]): any { return utilBuilderToSchema(fields) }
function schemaToBuilder(schema: any): BuilderField[] { return utilSchemaToBuilder(schema) }

async function save() {
  try {
    const json = advancedMode.value ? (schemaText.value ? JSON.parse(schemaText.value) : undefined) : builderToSchema(builderFields.value)
    const payload = { ...editor.form, json_schema: json }
    if (editor.editing && editor.form.id) {
      await updateOutputModel(editor.form.id, payload)
      ElMessage.success('已更新输出模型')
    } else {
      await createOutputModel(payload)
      ElMessage.success('已创建输出模型')
    }
    editor.visible = false
    // 通知其他组件刷新（如卡片类型）
    window.dispatchEvent(new CustomEvent('nf:output-models-updated'))
    await fetchModels()
  } catch (e:any) {
    ElMessage.error('保存失败：' + (e?.message || e))
  }
}

async function remove(row: OutputModel) {
  try {
    await deleteOutputModel(row.id as number)
    ElMessage.success('已删除')
    window.dispatchEvent(new CustomEvent('nf:output-models-updated'))
    await fetchModels()
  } catch (e:any) { ElMessage.error('删除失败：' + (e?.message || e)) }
}

onMounted(fetchModels)
</script>

<style scoped>
.output-model-manager { display: flex; flex-direction: column; gap: 12px; height: 100%; }
.header { display: flex; gap: 8px; align-items: center; justify-content: space-between; }
.mode-toggle { display: flex; align-items: center; gap: 8px; margin: 8px 0; }
.editor-grid { display: grid; grid-template-columns: 1fr; gap: 12px; }
</style> 