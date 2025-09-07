<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listProjectTemplates, createProjectTemplate, updateProjectTemplate, deleteProjectTemplate, type ProjectTemplate, type ProjectTemplateItem } from '@renderer/api/setting'
import { listCardTypes, type CardTypeRead } from '@renderer/api/setting'
import { ArrowUp, ArrowDown, Delete as DeleteIcon } from '@element-plus/icons-vue'

const templates = ref<ProjectTemplate[]>([])
const loading = ref(false)
const cardTypes = ref<CardTypeRead[]>([])

const editing = reactive<{ current: ProjectTemplate | null }>({ current: null })

const draft = reactive<{ id?: number; name: string; description?: string; items: ProjectTemplateItem[] }>({ name: '', description: '', items: [] })

function resetDraft(tpl?: ProjectTemplate) {
  if (tpl) {
    draft.id = tpl.id
    draft.name = tpl.name
    draft.description = tpl.description || ''
    draft.items = (tpl.items || []).map(i => ({ id: i.id, card_type_id: i.card_type_id, display_order: i.display_order, title_override: i.title_override }))
  } else {
    draft.id = undefined
    draft.name = ''
    draft.description = ''
    draft.items = []
  }
}

async function loadAll() {
  loading.value = true
  try {
    const [tpls, cts] = await Promise.all([listProjectTemplates(), listCardTypes()])
    templates.value = tpls
    cardTypes.value = cts
    if (!editing.current && templates.value.length > 0) selectTemplate(templates.value[0])
  } catch (e) {
    // ignore
  } finally {
    loading.value = false
  }
}

function selectTemplate(tpl: ProjectTemplate) {
  editing.current = tpl
  resetDraft(tpl)
}

function newTemplate() {
  editing.current = null
  resetDraft()
}

function addItem() {
  // 默认选择第一个卡片类型
  const firstType = cardTypes.value[0]
  if (!firstType) {
    ElMessage.warning('请先创建卡片类型')
    return
  }
  const nextOrder = draft.items.length
  draft.items.push({ card_type_id: firstType.id, display_order: nextOrder, title_override: firstType.name })
}

function removeItem(idx: number) {
  draft.items.splice(idx, 1)
  // 重新编号顺序
  draft.items.forEach((it, i) => it.display_order = i)
}

function moveItem(idx: number, dir: -1 | 1) {
  const j = idx + dir
  if (j < 0 || j >= draft.items.length) return
  const tmp = draft.items[idx]
  draft.items[idx] = draft.items[j]
  draft.items[j] = tmp
  draft.items.forEach((it, i) => it.display_order = i)
}

function handleTypeChange(idx: number, newTypeId: number) {
  const ct = cardTypes.value.find(c => c.id === newTypeId)
  if (!ct) return
  const current = draft.items[idx]
  const title = (current.title_override || '').trim()
  const isEmpty = title.length === 0
  const isAnyTypeName = cardTypes.value.some(c => c.name === title)
  if (isEmpty || isAnyTypeName) {
    current.title_override = ct.name
  }
}

async function save() {
  try {
    if (!draft.name.trim()) {
      ElMessage.error('请输入模板名称')
      return
    }
    const payload = { name: draft.name.trim(), description: draft.description, items: draft.items.map(i => ({ card_type_id: i.card_type_id, display_order: i.display_order, title_override: i.title_override })) }
    if (draft.id) {
      await updateProjectTemplate(draft.id, payload)
      ElMessage.success('已更新模板')
    } else {
      await createProjectTemplate(payload)
      ElMessage.success('已创建模板')
    }
    await loadAll()
  } catch (e: any) {
    ElMessage.error(`保存失败：${e?.message || e}`)
  }
}

async function remove() {
  if (!editing.current) return
  try {
    await ElMessageBox.confirm('确定删除该模板？', '提示', { type: 'warning' })
    await deleteProjectTemplate(editing.current!.id)
    ElMessage.success('已删除模板')
    editing.current = null
    resetDraft()
    await loadAll()
  } catch (e) {
    // cancel or error
  }
}

onMounted(loadAll)
</script>

<template>
  <div class="tpl-manager" v-loading="loading">
    <div class="left">
      <div class="toolbar">
        <el-button type="primary" @click="newTemplate">新建模板</el-button>
      </div>
      <el-scrollbar class="list">
        <el-empty v-if="templates.length===0" description="暂无模板" />
        <el-menu v-else :default-active="String(editing.current?.id || '')">
          <el-menu-item v-for="tpl in templates" :key="tpl.id" :index="String(tpl.id)" @click="selectTemplate(tpl)">
            <span>{{ tpl.name }}</span>
            <el-tag size="small" type="info" v-if="tpl.built_in" style="margin-left:8px">内置</el-tag>
          </el-menu-item>
        </el-menu>
      </el-scrollbar>
        </div>
    <div class="right">
      <el-form label-width="90px">
        <el-form-item label="名称">
          <el-input v-model="draft.name" placeholder="模板名称" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="draft.description" placeholder="模板描述" />
        </el-form-item>
        <el-form-item label="条目">
          <div class="items">
            <div class="item-header">
              <span class="col col-type">卡片类型</span>
              <span class="col col-title">标题</span>
              <span class="col col-actions">操作</span>
            </div>
            <div class="item-row" v-for="(it, idx) in draft.items" :key="idx">
              <el-select v-model="it.card_type_id" placeholder="卡片类型" style="width:220px" @change="(val:number) => handleTypeChange(idx, val)">
                <el-option v-for="ct in cardTypes" :key="ct.id" :label="ct.name" :value="ct.id" />
              </el-select>
              <el-input v-model="it.title_override" placeholder="标题（可选）" style="width:220px; margin-left:8px" />
              <el-tooltip content="上移" placement="top">
                <el-button @click="moveItem(idx,-1)" :disabled="idx===0" circle plain :icon="ArrowUp" style="margin-left:8px" />
              </el-tooltip>
              <el-tooltip content="下移" placement="top">
                <el-button @click="moveItem(idx,1)" :disabled="idx===draft.items.length-1" circle plain :icon="ArrowDown" />
              </el-tooltip>
              <el-tooltip content="删除" placement="top">
                <el-button type="danger" @click="removeItem(idx)" circle plain :icon="DeleteIcon" />
              </el-tooltip>
            </div>
            <el-button type="primary" text @click="addItem">+ 添加条目</el-button>
          </div>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="save">保存</el-button>
          <el-button type="danger" @click="remove" :disabled="!editing.current || editing.current.built_in">删除</el-button>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>

<style scoped>
.tpl-manager { display: flex; gap: 12px; height: 100%; }
.left { width: 260px; border-right: 1px solid var(--el-border-color); padding-right: 8px; display:flex; flex-direction: column; }
.toolbar { margin-bottom: 8px; }
.list { flex: 1; }
.right { flex: 1; padding-left: 8px; overflow: auto; }
.items { display: flex; flex-direction: column; gap: 8px; }
.item-header { display: flex; align-items: center; font-size: 12px; color: var(--el-text-color-secondary); padding-bottom: 4px; }
.item-header .col-type { width: 220px; }
.item-header .col-title { width: 220px; margin-left: 8px; }
.item-header .col-actions { margin-left: 8px; }
.item-row { display: flex; align-items: center; }
</style> 