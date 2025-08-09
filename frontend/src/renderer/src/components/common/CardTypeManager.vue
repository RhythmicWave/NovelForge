<template>
  <div class="card-type-manager">
    <!-- 工具条：搜索 + 新增 -->
    <div class="toolbar">
      <el-input v-model="query" placeholder="搜索类型（名称/描述）" clearable class="search" />
      <el-button type="primary" @click="openEditor()">新增类型</el-button>
    </div>

    <!-- 列表 -->
    <el-table :data="filteredTypes" height="60vh" size="small" :border="false" v-loading="loading">
      <el-table-column prop="name" label="名称" width="220" />
      <el-table-column prop="description" label="描述" min-width="260" />
      <el-table-column label="输出模型" width="200">
        <template #default="{ row }">
          <el-tag size="small">{{ row.output_model_name || '未设置' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="AI" width="90">
        <template #default="{ row }">
          <el-tag size="small" :type="row.is_ai_enabled ? 'success' : 'info'">{{ row.is_ai_enabled ? '启用' : '关闭' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="180" align="right">
        <template #default="{ row }">
          <el-button size="small" @click="openEditor(row)">编辑</el-button>
          <template v-if="!isBuiltInCardType(row)">
            <el-popconfirm title="删除该类型？（若有引用将影响创建操作）" @confirm="removeType(row)">
              <template #reference>
                <el-button size="small" type="danger" plain>删除</el-button>
              </template>
            </el-popconfirm>
          </template>
          <el-button v-else size="small" type="danger" plain disabled>删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 编辑抽屉：基础信息 + 选择输出模型 -->
    <el-drawer v-model="drawer.visible" :title="drawer.editing ? '编辑卡片类型' : '新增卡片类型'" size="60%">
      <div class="editor-grid">
        <el-form label-position="top" :model="form">
          <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
          <el-form-item label="描述"><el-input v-model="form.description" type="textarea" :rows="2" /></el-form-item>
          <el-form-item label="是否启用AI"><el-switch v-model="form.is_ai_enabled" /></el-form-item>
          <el-form-item label="是否单例"><el-switch v-model="form.is_singleton" /></el-form-item>
          <el-form-item label="默认上下文模板"><el-input v-model="form.default_ai_context_template" type="textarea" :rows="4" /></el-form-item>
          <el-form-item label="输出模型">
            <el-select v-model="form.output_model_name" placeholder="选择输出模型" filterable style="width:100%">
              <el-option v-for="n in outputModels" :key="n" :label="n" :value="n" />
            </el-select>
          </el-form-item>
          <el-form-item label="UI 布局（可选）">
            <el-input v-model="uiLayoutText" type="textarea" :rows="6" placeholder='{ "sections": [ ... ] }' />
          </el-form-item>
        </el-form>
      </div>
      <template #footer>
        <el-button @click="drawer.visible=false">取消</el-button>
        <el-button type="primary" @click="saveType">保存</el-button>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@renderer/api/request'
import type { components } from '@renderer/types/generated'
import { getAIConfigOptions } from '@renderer/api/ai'

// 后端 CardType 类型
type CardTypeRead = components['schemas']['CardTypeRead']
type CardTypeCreate = components['schemas']['CardTypeCreate']
type CardTypeUpdate = components['schemas']['CardTypeUpdate']

// 系统预设类型名称（禁删）
const PRESET_CARD_TYPES = new Set(['作品标签','金手指','一句话梗概','故事大纲','世界观设定','核心蓝图','分卷大纲','章节大纲','章节正文','角色卡','场景卡'])

// 数据源
const loading = ref(false)
const types = ref<CardTypeRead[]>([])
const query = ref('')
const outputModels = ref<string[]>([])

async function fetchTypes() { loading.value = true; try { types.value = await request.get('/card-types') } finally { loading.value = false } }
async function fetchOutputModels() { const opts = await getAIConfigOptions(); outputModels.value = opts.response_models }

// 监听输出模型更新事件
if (typeof window !== 'undefined') {
  window.addEventListener('nf:output-models-updated', () => { fetchOutputModels() })
}

const filteredTypes = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return types.value
  return types.value.filter(t => (t.name || '').toLowerCase().includes(q) || (t.description || '').toLowerCase().includes(q))
})

const drawer = ref({ visible: false, editing: false, id: 0 })
const form = ref<any>({ name: '', description: '', is_ai_enabled: true, is_singleton: false, default_ai_context_template: '', output_model_name: '' })
const uiLayoutText = ref('')

function isBuiltInCardType(row: any): boolean {
  return PRESET_CARD_TYPES.has(row?.name) || !!row?.model_name
}

function openEditor(row?: CardTypeRead) {
  drawer.value = { visible: true, editing: !!row, id: row?.id || 0 }
  form.value = row ? { ...row } : { name: '', description: '', is_ai_enabled: true, is_singleton: false, default_ai_context_template: '', output_model_name: '' }
  uiLayoutText.value = row?.ui_layout ? JSON.stringify(row.ui_layout, null, 2) : ''
}

async function saveType(): Promise<void> {
  let ui_layout: any = undefined
  try { ui_layout = uiLayoutText.value ? JSON.parse(uiLayoutText.value) : undefined } catch { ElMessage.error('UI 布局不是有效的 JSON'); return }
  const payload: Partial<CardTypeCreate & CardTypeUpdate> = { ...form.value, ui_layout }
  try {
    if (drawer.value.editing) {
      const id = drawer.value.id
      await request.put(`/card-types/${id}`, payload)
      ElMessage.success('已更新卡片类型')
    } else {
      await request.post('/card-types', payload)
      ElMessage.success('已创建卡片类型')
    }
    drawer.value.visible = false
    await fetchTypes()
  } catch (e:any) { ElMessage.error('保存失败：' + (e?.message || e)) }
}

async function removeType(row: CardTypeRead) { try { await request.delete(`/card-types/${row.id}`); ElMessage.success('已删除'); await fetchTypes() } catch (e:any) { ElMessage.error('删除失败：' + (e?.message || e)) } }

fetchTypes(); fetchOutputModels()
</script>

<style scoped>
.card-type-manager { display: flex; flex-direction: column; gap: 12px; height: 100%; }
.toolbar { display: flex; gap: 8px; align-items: center; }
.search { width: 320px; max-width: 60vw; }
.editor-grid { display: grid; grid-template-columns: 1fr; gap: 12px; height: calc(100% - 48px); }
</style> 