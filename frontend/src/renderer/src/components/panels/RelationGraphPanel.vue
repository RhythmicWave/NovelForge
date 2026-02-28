<template>
  <div class="relation-graph-panel">
    <div class="toolbar">
      <el-input v-model="filters.keyword" placeholder="关键词（实体/关系/事实）" clearable class="w-keyword" @keyup.enter="reload" />
      <el-select v-model="filters.kind" clearable placeholder="关系类型" class="w-select">
        <el-option v-for="k in kindOptions" :key="k" :label="k" :value="k" />
      </el-select>
      <el-select v-model="filters.stance" clearable placeholder="立场" class="w-select">
        <el-option label="友好" value="友好" />
        <el-option label="中立" value="中立" />
        <el-option label="敌意" value="敌意" />
      </el-select>
      <el-button type="primary" @click="reload">查询</el-button>
      <el-button @click="resetFilters">重置</el-button>
    </div>

    <div class="actions">
      <el-button type="primary" @click="openCreate">新增关系</el-button>
      <el-button @click="openBatchCreate">批量新增</el-button>
      <el-button @click="openImport">导入</el-button>
      <el-button :disabled="selectedKeys.length === 0" @click="exportSelected('json')">导出 JSON</el-button>
      <el-button :disabled="selectedKeys.length === 0" @click="exportSelected('csv')">导出 CSV</el-button>
      <el-button :disabled="selectedKeys.length === 0" type="danger" @click="batchDelete">批量删除</el-button>
      <el-button :disabled="selectedKeys.length === 0" @click="batchKindVisible = true">批量改类型</el-button>
      <el-button :disabled="selectedKeys.length === 0" @click="batchStanceVisible = true">批量改立场</el-button>
      <el-button :disabled="selectedKeys.length === 0" @click="batchEventsVisible = true">批量追加事件</el-button>
    </div>

    <el-table :data="rows" border stripe v-loading="loading" @selection-change="onSelectionChange">
      <el-table-column type="selection" width="48" />
      <el-table-column prop="source" label="A" min-width="140" />
      <el-table-column prop="target" label="B" min-width="140" />
      <el-table-column prop="kind_cn" label="关系" width="120" />
      <el-table-column prop="stance" label="立场" width="100" />
      <el-table-column prop="fact" label="事实" min-width="260" show-overflow-tooltip />
      <el-table-column prop="updated_at" label="更新时间" width="180" />
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="scope">
          <el-button text size="small" @click="openEdit(scope.row)">编辑</el-button>
          <el-button text size="small" type="danger" @click="removeOne(scope.row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pager">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        @change="reload"
      />
    </div>

    <el-dialog v-model="editVisible" :title="editMode === 'create' ? '新增关系' : '编辑关系'" width="680px">
      <el-form label-width="110px">
        <el-form-item label="实体 A"><el-input v-model="form.source" /></el-form-item>
        <el-form-item label="关系类型">
          <el-select v-model="form.kind_cn" placeholder="选择关系类型">
            <el-option v-for="k in kindOptions" :key="k" :label="k" :value="k" />
          </el-select>
        </el-form-item>
        <el-form-item label="实体 B"><el-input v-model="form.target" /></el-form-item>
        <el-form-item label="立场">
          <el-select v-model="form.stance" clearable>
            <el-option label="友好" value="友好" />
            <el-option label="中立" value="中立" />
            <el-option label="敌意" value="敌意" />
          </el-select>
        </el-form-item>
        <el-form-item label="事实"><el-input v-model="form.fact" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="A称呼B"><el-input v-model="form.a_to_b_addressing" /></el-form-item>
        <el-form-item label="B称呼A"><el-input v-model="form.b_to_a_addressing" /></el-form-item>
        <el-form-item label="近期对话">
          <el-input v-model="form.dialoguesText" type="textarea" :rows="3" placeholder="每行一条" />
        </el-form-item>
        <el-form-item label="近期事件">
          <el-input v-model="form.eventsText" type="textarea" :rows="3" placeholder="每行一条摘要" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" @click="submitEdit">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="batchKindVisible" title="批量修改关系类型" width="420px">
      <el-select v-model="batchKind" placeholder="选择新类型" style="width: 100%">
        <el-option v-for="k in kindOptions" :key="k" :label="k" :value="k" />
      </el-select>
      <template #footer>
        <el-button @click="batchKindVisible = false">取消</el-button>
        <el-button type="primary" @click="applyBatchKind">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="batchStanceVisible" title="批量修改立场" width="420px">
      <el-select v-model="batchStance" clearable placeholder="选择新立场" style="width: 100%">
        <el-option label="友好" value="友好" />
        <el-option label="中立" value="中立" />
        <el-option label="敌意" value="敌意" />
      </el-select>
      <template #footer>
        <el-button @click="batchStanceVisible = false">取消</el-button>
        <el-button type="primary" @click="applyBatchStance">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="batchEventsVisible" title="批量追加事件" width="520px">
      <el-input v-model="batchEventsText" type="textarea" :rows="6" placeholder="每行一条事件摘要" />
      <template #footer>
        <el-button @click="batchEventsVisible = false">取消</el-button>
        <el-button type="primary" @click="applyBatchEvents">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="batchCreateVisible" title="批量新增关系" width="680px">
      <div class="tip">支持 JSON 数组，或每行 CSV：source,target,kind_cn,stance</div>
      <el-input v-model="batchCreateText" type="textarea" :rows="12" />
      <template #footer>
        <el-button @click="batchCreateVisible = false">取消</el-button>
        <el-button type="primary" @click="submitBatchCreate">提交</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="importVisible" title="导入关系图" width="680px">
      <div class="toolbar compact">
        <el-select v-model="importFormat" class="w-select">
          <el-option label="JSON" value="json" />
          <el-option label="CSV" value="csv" />
        </el-select>
        <el-button @click="pickFile">从文件读取</el-button>
      </div>
      <input ref="fileInputRef" type="file" class="hidden" @change="onFileChange" />
      <el-input v-model="importContent" type="textarea" :rows="12" />
      <template #footer>
        <el-button @click="importVisible = false">取消</el-button>
        <el-button type="primary" @click="submitImport">导入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useProjectStore } from '@renderer/stores/useProjectStore'
import {
  batchAppendEventsRelationGraph,
  batchCreateRelationGraph,
  batchDeleteRelationGraph,
  batchUpdateKindRelationGraph,
  batchUpdateStanceRelationGraph,
  deleteRelationGraph,
  exportRelationGraph,
  importRelationGraph,
  listRelationGraph,
  upsertRelationGraph,
  type RelationGraphKey,
  type RelationGraphRecord,
} from '@renderer/api/relationGraph'

const projectStore = useProjectStore()
const loading = ref(false)
const rows = ref<RelationGraphRecord[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const selectedRows = ref<RelationGraphRecord[]>([])

const filters = reactive({ keyword: '', kind: '', stance: '' })

const kindOptions = [
  '同盟', '队友', '同门', '敌对', '亲属', '师徒', '对手', '伙伴', '上级', '下属', '指导',
  '隶属', '成员', '领导', '创立', '控制', '位于', '影响', '克制', '关于', '其他'
]
const kindCnToEn: Record<string, string> = {
  '同盟': 'ally',
  '队友': 'team',
  '同门': 'fellow',
  '敌对': 'enemy',
  '亲属': 'family',
  '师徒': 'mentor',
  '对手': 'rival',
  '伙伴': 'partner',
  '上级': 'superior',
  '下属': 'subordinate',
  '指导': 'guide',
  '隶属': 'member_of',
  '成员': 'member',
  '领导': 'lead',
  '创立': 'found',
  '控制': 'control',
  '位于': 'locate_in',
  '影响': 'influence',
  '克制': 'counter',
  '关于': 'about',
  '其他': 'other',
}

const editVisible = ref(false)
const editMode = ref<'create' | 'edit'>('create')
const editingKey = ref<RelationGraphKey | null>(null)
const form = reactive({
  source: '',
  target: '',
  kind_cn: '',
  stance: '',
  fact: '',
  a_to_b_addressing: '',
  b_to_a_addressing: '',
  dialoguesText: '',
  eventsText: '',
})

const batchKindVisible = ref(false)
const batchKind = ref('')
const batchStanceVisible = ref(false)
const batchStance = ref('')
const batchEventsVisible = ref(false)
const batchEventsText = ref('')
const batchCreateVisible = ref(false)
const batchCreateText = ref('')

const importVisible = ref(false)
const importFormat = ref<'json' | 'csv'>('json')
const importContent = ref('')
const fileInputRef = ref<HTMLInputElement | null>(null)

const selectedKeys = computed<RelationGraphKey[]>(() =>
  selectedRows.value
    .filter((r) => !!r.source && !!r.target && !!r.kind_en)
    .map((r) => ({ source: r.source!, target: r.target!, kind_en: r.kind_en! }))
)

function getProjectId(): number {
  const pid = projectStore.currentProject?.id
  if (!pid) throw new Error('请先选择项目')
  return pid
}

function parseLines(text: string): string[] {
  return (text || '').split(/\r?\n/).map((x) => x.trim()).filter(Boolean)
}

function resetForm() {
  form.source = ''
  form.target = ''
  form.kind_cn = ''
  form.stance = ''
  form.fact = ''
  form.a_to_b_addressing = ''
  form.b_to_a_addressing = ''
  form.dialoguesText = ''
  form.eventsText = ''
}

function openCreate() {
  editMode.value = 'create'
  editingKey.value = null
  resetForm()
  editVisible.value = true
}

function openEdit(row: RelationGraphRecord) {
  editMode.value = 'edit'
  editingKey.value = { source: row.source!, target: row.target!, kind_en: row.kind_en! }
  form.source = row.source || ''
  form.target = row.target || ''
  form.kind_cn = row.kind_cn || row.kind || ''
  form.stance = row.stance || ''
  form.fact = row.fact || ''
  form.a_to_b_addressing = row.a_to_b_addressing || ''
  form.b_to_a_addressing = row.b_to_a_addressing || ''
  form.dialoguesText = (row.recent_dialogues || []).join('\n')
  form.eventsText = (row.recent_event_summaries || []).map((e: any) => e.summary || '').filter(Boolean).join('\n')
  editVisible.value = true
}

async function reload() {
  try {
    const projectId = getProjectId()
    loading.value = true
    const resp = await listRelationGraph({
      project_id: projectId,
      keyword: filters.keyword || undefined,
      kinds: filters.kind ? [filters.kind] : [],
      stances: filters.stance ? [filters.stance] : [],
      offset: (page.value - 1) * pageSize.value,
      limit: pageSize.value,
    })
    rows.value = resp.items || []
    total.value = resp.total || 0
  } catch (e: any) {
    ElMessage.error(e?.message || '加载关系图失败')
  } finally {
    loading.value = false
  }
}

function resetFilters() {
  filters.keyword = ''
  filters.kind = ''
  filters.stance = ''
  page.value = 1
  reload()
}

function onSelectionChange(list: RelationGraphRecord[]) {
  selectedRows.value = list || []
}

async function submitEdit() {
  try {
    const projectId = getProjectId()
    const nextKindEn = kindCnToEn[form.kind_cn] || editingKey.value?.kind_en || ''
    await upsertRelationGraph({
      project_id: projectId,
      relation: {
        source: form.source,
        target: form.target,
        kind_cn: form.kind_cn,
        fact: form.fact || undefined,
        a_to_b_addressing: form.a_to_b_addressing || undefined,
        b_to_a_addressing: form.b_to_a_addressing || undefined,
        stance: form.stance || undefined,
        recent_dialogues: parseLines(form.dialoguesText),
        recent_event_summaries: parseLines(form.eventsText).map((summary) => ({ summary })),
      },
    })

    if (editMode.value === 'edit' && editingKey.value) {
      const oldKey = editingKey.value
      const changedKey =
        oldKey.source !== form.source ||
        oldKey.target !== form.target ||
        oldKey.kind_en !== nextKindEn
      if (changedKey) {
        await deleteRelationGraph({ project_id: projectId, key: oldKey })
      }
    }

    editVisible.value = false
    ElMessage.success('保存成功')
    reload()
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  }
}

async function removeOne(row: RelationGraphRecord) {
  try {
    const projectId = getProjectId()
    await ElMessageBox.confirm(`确认删除关系 ${row.source} -> ${row.target} 吗？`, '删除确认', { type: 'warning' })
    await deleteRelationGraph({ project_id: projectId, key: { source: row.source!, target: row.target!, kind_en: row.kind_en! } })
    ElMessage.success('删除成功')
    reload()
  } catch {}
}

async function batchDelete() {
  try {
    const projectId = getProjectId()
    await ElMessageBox.confirm(`确认删除已勾选的 ${selectedKeys.value.length} 条关系吗？`, '批量删除', { type: 'warning' })
    const resp = await batchDeleteRelationGraph({ project_id: projectId, keys: selectedKeys.value })
    ElMessage.success(`已删除 ${resp.affected || 0} 条`)
    reload()
  } catch {}
}

async function applyBatchKind() {
  try {
    const projectId = getProjectId()
    const resp = await batchUpdateKindRelationGraph({ project_id: projectId, keys: selectedKeys.value, new_kind_cn: batchKind.value })
    ElMessage.success(`已更新 ${resp.affected || 0} 条`)
    batchKindVisible.value = false
    batchKind.value = ''
    reload()
  } catch (e: any) {
    ElMessage.error(e?.message || '批量更新失败')
  }
}

async function applyBatchStance() {
  try {
    const projectId = getProjectId()
    const resp = await batchUpdateStanceRelationGraph({ project_id: projectId, keys: selectedKeys.value, stance: batchStance.value || undefined })
    ElMessage.success(`已更新 ${resp.affected || 0} 条`)
    batchStanceVisible.value = false
    batchStance.value = ''
    reload()
  } catch (e: any) {
    ElMessage.error(e?.message || '批量更新失败')
  }
}

async function applyBatchEvents() {
  try {
    const projectId = getProjectId()
    const events = parseLines(batchEventsText.value).map((summary) => ({ summary }))
    const resp = await batchAppendEventsRelationGraph({ project_id: projectId, keys: selectedKeys.value, events, max_size: 20 })
    ElMessage.success(`已更新 ${resp.affected || 0} 条`)
    batchEventsVisible.value = false
    batchEventsText.value = ''
    reload()
  } catch (e: any) {
    ElMessage.error(e?.message || '批量更新失败')
  }
}

function openBatchCreate() {
  batchCreateVisible.value = true
}

function parseBatchCreateInput(text: string) {
  const trimmed = text.trim()
  if (!trimmed) return []
  if (trimmed.startsWith('[')) {
    const arr = JSON.parse(trimmed)
    if (!Array.isArray(arr)) throw new Error('JSON 必须是数组')
    return arr
  }
  return parseLines(trimmed).map((line) => {
    const [source, target, kind_cn, stance] = line.split(',').map((x) => x.trim())
    return { source, target, kind_cn, stance }
  })
}

async function submitBatchCreate() {
  try {
    const projectId = getProjectId()
    const relations = parseBatchCreateInput(batchCreateText.value)
    const resp = await batchCreateRelationGraph({ project_id: projectId, relations })
    ElMessage.success(`已处理 ${resp.affected || 0} 条`)
    batchCreateVisible.value = false
    batchCreateText.value = ''
    reload()
  } catch (e: any) {
    ElMessage.error(e?.message || '批量新增失败')
  }
}

function saveDownload(filename: string, content: string, mime: string) {
  const blob = new Blob([content], { type: mime || 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

async function exportSelected(format: 'json' | 'csv') {
  try {
    const projectId = getProjectId()
    const resp = await exportRelationGraph({ project_id: projectId, format, keys: selectedKeys.value })
    saveDownload(resp.filename || `relation-graph.${format}`, resp.content || '', resp.mime_type || 'text/plain')
    ElMessage.success('导出完成')
  } catch (e: any) {
    ElMessage.error(e?.message || '导出失败')
  }
}

function openImport() {
  importVisible.value = true
}

function pickFile() {
  fileInputRef.value?.click()
}

async function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  importContent.value = await file.text()
}

async function submitImport() {
  try {
    const projectId = getProjectId()
    const resp = await importRelationGraph({ project_id: projectId, format: importFormat.value, content: importContent.value })
    ElMessage.success(`导入完成：新增 ${resp.created || 0}，更新 ${resp.updated || 0}，失败 ${resp.failed || 0}`)
    if ((resp.errors || []).length > 0) {
      ElMessage.warning(`存在 ${resp.errors?.length} 条错误，请检查输入格式`)
    }
    importVisible.value = false
    reload()
  } catch (e: any) {
    ElMessage.error(e?.message || '导入失败')
  }
}

onMounted(() => {
  reload()
})
</script>

<style scoped>
.relation-graph-panel { display: flex; flex-direction: column; gap: 12px; padding: 12px; height: 100%; }
.toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar.compact { padding: 0 0 8px 0; }
.actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.w-keyword { width: 280px; }
.w-select { width: 140px; }
.pager { display: flex; justify-content: flex-end; padding-top: 8px; }
.hidden { display: none; }
.tip { color: var(--el-text-color-secondary); font-size: 12px; margin-bottom: 8px; }
</style>
