<script setup lang="ts">
import { computed, reactive, ref, watch, nextTick } from 'vue'
import type { CardTypeRead } from '@renderer/api/cards'
import { getCardTypes } from '@renderer/api/cards'
import FieldSelector from './FieldSelector.vue'
import { QuestionFilled } from '@element-plus/icons-vue'

const props = defineProps<{ node: any | null; contextTypeName?: string }>()
const emit = defineEmits<{ 'update-params': [any] }>()

const state = reactive({ types: [] as CardTypeRead[] })
getCardTypes().then(v => state.types = v).catch(() => {})

const typeName = computed(() => props.node?.data?.type || '')
const params = computed({
  get() { return (props.node?.data?.params || {}) },
  set(v: any) {
    // 主动透传父层，防止 v-model 不触发
    emit('update-params', v)
  }
})

watch(() => props.node, (n) => { /* noop: 直接读计算属性 */ }, { immediate: true })

function update(key: string, value: any) {
  const next = { ...(params.value || {}) }
  ;(next as any)[key] = value
  emit('update-params', next)
}

// contentTemplate 文本编辑辅助：对象 <-> JSON 字符串
function formatTemplate(val: any): string {
  try {
    if (typeof val === 'string') return val
    if (val == null) return ''
    return JSON.stringify(val, null, 2)
  } catch { return String(val ?? '') }
}
function updateTemplateFromText(text: string) {
  try {
    const parsed = JSON.parse(text)
    update('contentTemplate', parsed)
  } catch {
    // 允许直接保存字符串模板
    update('contentTemplate', text)
  }
}

const templatePlaceholder = `例如：{\n  "title": "{item.name}",\n  "entity_list": { "$toNameList": "item.entity_list" }\n}`

// 简单模式：用行编辑构建对象模板（键 -> 值来源）
const simpleMode = ref(true)
let syncing = false
let rowUid = 0
type Row = { id: number; key: string; source: 'item'|'card'|'text'|'number'; path?: string; text?: string; number?: number }
const rows = ref<Row[]>([])
const rowsVersion = ref<number>(0)
// 同步 props.params -> 本地 UI 状态
watch(params, (p) => {
  syncing = true
  try {
    simpleMode.value = !!(p && (p.__ui_simple_mode ?? true))
    const raw: any[] = Array.isArray((p as any)?.__ui_rows) ? (p as any).__ui_rows : []
    rows.value = raw.map((r: any) => ({
      id: Number.isFinite(Number(r?.id)) ? Number(r.id) : (++rowUid),
      key: String(r?.key || ''),
      source: (['item','card','text','number'].includes(r?.source) ? (r.source as Row['source']) : 'item'),
      path: String(r?.path || ''),
      text: String(r?.text || ''),
      number: Number.isFinite(Number(r.number)) ? Number(r.number) : undefined,
    }))
    // 维护自增游标
    try { rowUid = Math.max(rowUid, ...rows.value.map(r => r.id)) } catch {}
    rowsVersion.value++
    // 若没有 rows 但已有模板，则从模板反推简单模式行
    if (rows.value.length === 0 && (p as any)?.contentTemplate) {
      loadRowsFromTemplate()
    }
  } finally {
    queueMicrotask(() => { syncing = false })
  }
}, { immediate: true, deep: true })
// 同步 UI -> params（带循环保护）
watch(simpleMode, (v) => { if (!syncing) update('__ui_simple_mode', v) })
watch(rows, (v) => { if (!syncing) { update('__ui_rows', v); syncRowsToTemplate() } }, { deep: true })
function addRow() {
  const newRow: Row = { id: ++rowUid, key: '', source: 'item', path: '' }
  rows.value = [...rows.value, newRow]
  // 立即写回 params，避免由父层回写后触发的二次同步覆盖本地新增行的可见性
  update('__ui_rows', rows.value)
  nextTick(() => { /* ensure UI updates */ })
}
function removeRow(i: number) {
  const next = rows.value.slice(); next.splice(i,1); rows.value = next; update('__ui_rows', rows.value); syncRowsToTemplate()
}
function _computeDefaultPath(r: Row): string {
  if (r.source === 'item') {
    if (r.path && r.path.trim()) return r.path
    return r.key ? `item.${r.key}` : 'item.xxx'
  }
  if (r.source === 'card') {
    if (r.path && r.path.trim()) return r.path
    if (r.key === 'volume_number') return 'index'
    if (r.key && r.key !== 'content') return `content.${r.key}`
    return 'content.xxx'
  }
  return r.path || ''
}

function setRow(i: number, patch: Partial<Row>) {
  const next = rows.value.slice();
  const merged = { ...next[i], ...patch } as Row
  // 若用户切换了 source 或刚设置了 key，而 path 为空，则给出合理默认
  if (('source' in (patch as any) || ('key' in (patch as any))) && (!merged.path || !String(merged.path).trim())) {
    merged.path = _computeDefaultPath(merged)
  }
  next[i] = merged
  rows.value = next
  update('__ui_rows', rows.value)
  syncRowsToTemplate()
}
function syncRowsToTemplate() {
  const obj: any = {}
  for (const r of rows.value) {
    if (!r || !r.key) continue
    if (r.source === 'item') {
      const p = (r.path || '').replace(/^item\.?/, '')
      obj[r.key] = `{item${p ? '.'+p : ''}}`
    } else if (r.source === 'card') {
      const p = r.path && r.path.startsWith('$.') ? r.path : (`$.content${r.path ? '.'+r.path : ''}`)
      obj[r.key] = `{${p}}`
    } else if (r.source === 'text') {
      obj[r.key] = String(r.text ?? '')
    } else if (r.source === 'number') {
      const n = Number(r.number); obj[r.key] = Number.isFinite(n) ? n : 0
    }
  }
  update('contentTemplate', obj)
  update('contentPath', undefined)
  update('useItemAsContent', false)
}

function loadRowsFromTemplate() {
  const tpl = params.value?.contentTemplate
  if (!tpl || typeof tpl !== 'object' || Array.isArray(tpl)) return
  const next: Row[] = []
  for (const k of Object.keys(tpl)) {
    const v = (tpl as any)[k]
    if (typeof v === 'string') {
      // 解析占位符 {item.xxx} 或 {$.content.yyy}
      const m = v.match(/^\{([^}]+)\}$/)
      if (m) {
        const expr = m[1]
        if (expr.startsWith('item')) next.push({ id: ++rowUid, key: k, source: 'item', path: expr.replace(/^item\.?/, '') })
        else next.push({ id: ++rowUid, key: k, source: 'card', path: expr.replace(/^\$\.content\.?/, '') })
        continue
      }
    }
    if (typeof v === 'number') next.push({ id: ++rowUid, key: k, source: 'number', number: v })
    else next.push({ id: ++rowUid, key: k, source: 'text', text: String(v) })
  }
  rows.value = next
}

// 合并模式：表达式/模板统一编辑
const exprText = computed(() => {
  if (params.value?.useItemAsContent) return ''
  if (params.value?.contentPath) return String(params.value.contentPath)
  return formatTemplate(params.value?.contentTemplate)
})
function updateExprOrTemplate(text: string) {
  const t = (text ?? '').trim()
  if (!t) {
    update('contentPath', undefined)
    update('contentTemplate', undefined)
    return
  }
  // 以 { 或 [ 开头，按模板处理；否则按表达式
  if (t.startsWith('{') || t.startsWith('[')) {
    updateTemplateFromText(t)
    update('contentPath', undefined)
  } else {
    update('contentPath', t)
    update('contentTemplate', undefined)
  }
}

// ---- 基于类型 schema 的字段建议（展开 $.content.* 路径） ----
function extractContentPaths(schema: any, base = '$.content', acc: string[] = []): string[] {
  try {
    const props = (schema?.properties || {}) as Record<string, any>
    Object.keys(props).forEach((k) => {
      const node = props[k]
      if (node?.type === 'object' && node?.properties) {
        extractContentPaths(node, `${base}.${k}`, acc)
      } else {
        acc.push(`${base}.${k}`)
      }
    })
  } catch {}
  return acc
}

const selectedTypeName = computed(() => {
  const t = params.value?.type_name || params.value?.cardType || props.contextTypeName
  if (!t && state.types.length) return state.types[0].name
  return t || ''
})
const selectedType = computed(() => state.types.find(t => t.name === selectedTypeName.value))
const fieldSuggestions = computed(() => extractContentPaths((selectedType.value as any)?.json_schema || {}))
// 针对“子卡内容键名”的建议：来自子卡类型 schema 的根部一级 keys
function extractContentKeys(schema: any): string[] {
  try {
    const props = (schema?.properties || {}) as Record<string, any>
    return Object.keys(props)
  } catch { return [] }
}
const childType = computed(() => state.types.find(t => t.name === (params.value as any)?.cardType))
const childContentKeys = computed(() => extractContentKeys((childType.value as any)?.json_schema || {}))
// 父卡（当前上下文）类型，用于“来源=卡片字段”的字段建议
const parentType = computed(() => state.types.find(t => t.name === (props.contextTypeName || '')))

// --- 本地输入态：标题模板，避免深层重渲导致输入闪回 ---
const titleLocal = ref('')
watch(() => (params.value?.title ?? params.value?.titlePath ?? ''), (v) => {
  titleLocal.value = String(v ?? '')
}, { immediate: true })
watch(titleLocal, (v) => { update('title', v) })
</script>

<template>
  <div class="panel" v-if="node">
    <div class="panel-title">参数 · {{ typeName }}</div>

    <!-- Card.Read（绑定卡片类型作为工作流上下文） -->
    <template v-if="typeName === 'Card.Read'">
      <el-form label-width="110px" size="small">
        <el-form-item label="卡片类型">
          <el-select :model-value="params.type_name || selectedTypeName" @update:model-value="v=>update('type_name', v)" placeholder="请选择此工作流绑定的卡片类型">
            <el-option v-for="t in state.types" :key="t.id" :label="t.name" :value="t.name" />
          </el-select>
        </el-form-item>
        <div class="tip">说明：工作流绑定到某个卡片类型后，后续节点会使用该类型的字段进行路径选择与校验。</div>
      </el-form>
    </template>

    <!-- List.ForEach -->
    <template v-else-if="typeName === 'List.ForEach'">
      <el-form label-width="110px" size="small">
        <el-form-item label="listPath">
          <div class="horiz">
            <el-input class="flex1" :model-value="params.listPath || params.list" @update:model-value="v=>update('listPath', v)" placeholder="如：$.content.xxx" />
             <FieldSelector :schema="(selectedType as any)?.json_schema || null" basePrefix="$.content" @update:modelValue="(v:string)=>update('listPath', v)" />
          </div>
        </el-form-item>
      </el-form>
    </template>

    <!-- Card.UpsertChildByTitle -->
    <template v-else-if="typeName === 'Card.UpsertChildByTitle'">
      <el-form label-width="110px" size="small">
        <el-form-item label="子卡类型">
          <el-select :model-value="params.cardType" @update:model-value="v=>update('cardType', v)">
            <el-option v-for="t in state.types" :key="t.id" :label="t.name" :value="t.name" />
          </el-select>
        </el-form-item>
        <el-form-item label="标题模板">
          <el-input v-model="titleLocal" @input="update('title', titleLocal)" placeholder="如：{item.name}" />
        </el-form-item>
        <el-form-item label="内容来源">
          <el-radio-group :model-value="params.useItemAsContent ? 'item' : 'expr'" @update:model-value="(v:string)=>{
            if (v==='item') { update('useItemAsContent', true); update('contentPath', undefined); update('contentTemplate', undefined) }
            else { update('useItemAsContent', false) }
          }">
            <el-radio label="item">使用 item</el-radio>
            <el-radio label="expr">表达式 / 模板</el-radio>
          </el-radio-group>
          <el-tooltip effect="dark" placement="top">
            <template #content>
              <div style="max-width:300px; line-height:1.4">
                使用 item：直接把 ForEach 循环项作为子卡 content。<br/>
                表达式/模板：若输入以 { 或 [ 开头，按 JSON 模板解析；否则按表达式取值。<br/>
                表达式支持：item.xxx / $.content.yyy / scope.xxx / current.card.xxx。
              </div>
            </template>
            <el-icon style="margin-left:6px; color: var(--el-text-color-secondary)"><QuestionFilled/></el-icon>
          </el-tooltip>
        </el-form-item>
        <el-form-item v-if="!params.useItemAsContent" label="表达式/模板">
          <div class="horiz">
            <el-switch v-model="simpleMode" active-text="简单模式" inactive-text="自由编辑" />
            <el-tooltip placement="top" effect="dark">
              <template #content>简单模式：逐行选择字段来源自动生成模板；自由编辑：直接写表达式或 JSON 模板。</template>
              <el-icon style="margin-left:6px; color: var(--el-text-color-secondary)"><QuestionFilled/></el-icon>
            </el-tooltip>
          </div>
          <template v-if="simpleMode">
            <div class="rows" :data-revision="rowsVersion" style="width: 100%">
              <div class="row" v-for="(r,i) in rows" :key="r.id">
                <el-select class="k" placeholder="键名" v-model="rows[i].key" filterable allow-create default-first-option>
                  <el-option v-for="k in childContentKeys" :key="k" :label="k" :value="k" />
                </el-select>
                <el-select class="s" v-model="rows[i].source">
                  <el-option label="item" value="item" />
                  <el-option label="卡片字段" value="card" />
                  <el-option label="文本" value="text" />
                  <el-option label="数字" value="number" />
                </el-select>
                <template v-if="rows[i].source==='item'">
                  <el-input class="v flex1" placeholder="item.xxx" v-model="rows[i].path" />
                </template>
                <template v-else-if="rows[i].source==='card'">
                  <div class="horiz">
                    <el-input class="v flex1" placeholder="如：title 或 content.xxx" v-model="rows[i].path" />
                  </div>
                </template>
                <template v-else-if="rows[i].source==='text'">
                  <el-input class="v" placeholder="文本" v-model="rows[i].text" />
                </template>
                <template v-else>
                  <el-input class="v" placeholder="数字" v-model.number="rows[i].number" />
                </template>
                <el-button text type="danger" @click="removeRow(i)">删除</el-button>
              </div>
              <el-button type="primary" plain @click="addRow">添加字段</el-button>
            </div>
          </template>
          <template v-else>
            <div class="horiz">
              <el-input class="flex1" type="textarea" :rows="6" :model-value="exprText" @update:model-value="v=>updateExprOrTemplate(v)" :placeholder="templatePlaceholder" />
              <FieldSelector :schema="(selectedType as any)?.json_schema || null" basePrefix="$.content" @update:modelValue="(v:string)=>updateExprOrTemplate(v)" />
            </div>
          </template>
        </el-form-item>
      </el-form>
    </template>

    <!-- Card.ModifyContent -->
    <template v-else-if="typeName === 'Card.ModifyContent'">
      <el-form label-width="110px" size="small">
        <el-form-item label="setPath">
          <div class="horiz">
            <el-input class="flex1" :model-value="params.setPath" @update:model-value="v=>update('setPath', v)" placeholder="$.content.xxx" />
             <FieldSelector :schema="(selectedType as any)?.json_schema || null" basePrefix="$.content" @update:modelValue="(v:string)=>update('setPath', v)" />
          </div>
        </el-form-item>
        <el-form-item label="setValue">
          <el-input :model-value="params.setValue" @update:model-value="v=>update('setValue', v)" placeholder="可用 {item.xxx}" />
        </el-form-item>
      </el-form>
    </template>

    <template v-else>
      <div class="empty">暂不支持该节点的参数编辑</div>
    </template>
  </div>
</template>

<style scoped>
.panel { padding: 8px; border-left: 1px solid var(--el-border-color); height: 60vh; overflow: auto; background: var(--el-bg-color); color: var(--el-text-color-primary); }
.panel-title { font-weight: 600; margin-bottom: 8px; }
.empty { color: var(--el-text-color-secondary); }
.horiz { display: flex; gap: 6px; align-items: center; }
.horiz .flex1 { flex: 1 1 auto; }
.row .horiz { width: 100%; }
 .v { flex: 1 1 auto; width: 100%; min-width: 5vw;}
.horiz .sugg { width: 180px; }
.tip { color: var(--el-text-color-secondary); font-size: 12px; margin: 4px 0 0 110px; }
.rows { display: flex; flex-direction: column; gap: 8px; margin: 6px 0; }
.row { display: grid; grid-template-columns: 120px 110px 1fr auto; gap: 6px; align-items: center; }
.row .k { width: 120px; }
.row .s { width: 110px; }
.row .v { width: 100%; }
</style>


