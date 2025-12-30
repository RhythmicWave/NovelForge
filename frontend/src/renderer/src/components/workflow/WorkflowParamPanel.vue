<script setup lang="ts">
import { computed, reactive, ref, watch, nextTick } from 'vue'
import type { CardTypeRead } from '@renderer/api/cards'
import { getCardTypes } from '@renderer/api/cards'
// import FieldTreeNode from './FieldTreeNode.vue' // 暂时注释，可能是 TypeScript 缓存问题
import { QuestionFilled, DocumentCopy } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { parseSchemaFields, toggleFieldExpanded, extractFieldPathOptions, type ParsedField } from '@renderer/services/schemaFieldParser'

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

// 智能建议功能
const suggestions = computed(() => {
  const nodeType = typeName.value
  const currentParams = params.value || {}
  const hints: Array<{key: string, value: any, description: string}> = []
  
  // 根据节点类型提供智能建议
  switch (nodeType) {
    case 'Card.Read':
      if (!currentParams.target) {
        hints.push({ key: 'target', value: '$self', description: '读取当前卡片' })
      }
      break
    case 'Card.UpsertChildByTitle':
      if (!currentParams.cardType && props.contextTypeName) {
        const suggestedTypes = ['章节大纲', '章节正文', '角色卡', '场景卡']
        for (const type of suggestedTypes) {
          if (type !== props.contextTypeName) {
            hints.push({ key: 'cardType', value: type, description: `创建${type}子卡` })
            break
          }
        }
      }
      if (!currentParams.title) {
        hints.push({ key: 'title', value: '{item.name}', description: '使用item.name作为标题' })
        hints.push({ key: 'title', value: '第{item.chapter_number}章', description: '使用章节号作为标题' })
      }
      break
    case 'List.ForEach':
      if (!currentParams.listPath) {
        hints.push({ key: 'listPath', value: '$.content.character_cards', description: '遍历角色卡列表' })
        hints.push({ key: 'listPath', value: '$.content.scene_cards', description: '遍历场景卡列表' })
        hints.push({ key: 'listPath', value: '$.content.chapter_outline_list', description: '遍历章节大纲列表' })
      }
      break
    case 'List.ForEachRange':
      if (!currentParams.countPath) {
        hints.push({ key: 'countPath', value: '$.content.volume_count', description: '遍历卷数' })
        hints.push({ key: 'countPath', value: '$.content.stage_count', description: '遍历阶段数' })
      }
      if (!currentParams.start) {
        hints.push({ key: 'start', value: 1, description: '从1开始遍历' })
      }
      break
    case 'Card.ClearFields':
      if (!currentParams.fields || (Array.isArray(currentParams.fields) && currentParams.fields.length === 0)) {
        hints.push({ key: 'fields', value: ['$.content.character_cards'], description: '清空角色卡列表' })
        hints.push({ key: 'fields', value: ['$.content.scene_cards'], description: '清空场景卡列表' })
      }
      break
    case 'Card.ModifyContent':
      if (currentParams.contentMerge) {
        // 合并模式建议
        if (!currentParams.contentMerge || Object.keys(currentParams.contentMerge).length === 0) {
          hints.push({ key: 'contentMerge', value: { character_cards: [] }, description: '清空角色卡列表' })
          hints.push({ key: 'contentMerge', value: { scene_cards: [] }, description: '清空场景卡列表' })
          hints.push({ key: 'contentMerge', value: { status: 'completed' }, description: '设置状态为已完成' })
        }
      } else {
        // 路径模式建议
        if (!currentParams.setPath) {
          hints.push({ key: 'setPath', value: '$.content.status', description: '设置状态字段' })
          hints.push({ key: 'setValue', value: 'completed', description: '设置为已完成' })
        }
      }
      break
  }
  
  return hints.slice(0, 3) // 最多显示3个建议
})

// 应用建议
function applySuggestion(suggestion: {key: string, value: any, description: string}) {
  update(suggestion.key, suggestion.value)
}

// 字段路径选项（用于替代 FieldSelector）
const fieldPathOptions = computed(() => {
  const typeName = props.contextTypeName
  if (!typeName) return []
  
  const selectedType = state.types.find(t => t.name === typeName)
  if (!selectedType?.json_schema) return []
  
  const fields = parseSchemaFields(selectedType.json_schema)
  return extractFieldPathOptions(fields)
})

// Card.ModifyContent 模式判断
const modifyContentMode = computed(() => {
  const currentParams = params.value || {}
  // 如果有 contentMerge 参数，使用合并模式
  if (currentParams.contentMerge) return 'merge'
  // 否则使用路径模式
  return 'path'
})

// contentMerge 的文本表示
const contentMergeText = computed(() => {
  const contentMerge = params.value?.contentMerge as any
  if (contentMerge == null) return ''
  // 若是字符串（编辑中或解析失败时的原始文本），直接原样显示
  if (typeof contentMerge === 'string') return contentMerge
  try {
    // 对象/数组时使用 JSON 美化
    return JSON.stringify(contentMerge, null, 2)
  } catch {
    return String(contentMerge)
  }
})

// 切换 ModifyContent 模式
function switchModifyContentMode(mode: 'path' | 'merge') {
  const currentParams = { ...(params.value || {}) }
  if (mode === 'path') {
    // 切换到路径模式，清除 contentMerge
    delete currentParams.contentMerge
    if (!currentParams.setPath) currentParams.setPath = ''
    if (!currentParams.setValue) currentParams.setValue = ''
  } else {
    // 切换到合并模式，清除路径参数
    delete currentParams.setPath
    delete currentParams.setValue
    if (!currentParams.contentMerge) currentParams.contentMerge = {}
  }
  emit('update-params', currentParams)
}

// 更新 contentMerge
function updateContentMerge(text: string) {
  const raw = text ?? ''
  const trimmed = raw.trim()
  if (!trimmed) {
    update('contentMerge', undefined)
    return
  }
  try {
    const parsed = JSON.parse(trimmed)
    update('contentMerge', parsed)
  } catch (e) {
    // JSON 解析失败时，保持文本状态，不更新参数
    console.warn('Invalid JSON in contentMerge:', e)
    update('contentMerge', raw)
  }
}

// 参数校验
const paramErrors = computed(() => {
  const nodeType = typeName.value
  const currentParams = params.value || {}
  const errors: string[] = []
  
  // 必填参数检查
  switch (nodeType) {
    case 'List.ForEach':
      if (!currentParams.listPath) {
        errors.push('listPath 是必填参数')
      }
      break
    case 'List.ForEachRange':
      if (!currentParams.countPath) {
        errors.push('countPath 是必填参数')
      }
      break
    case 'Card.UpsertChildByTitle':
      if (!currentParams.cardType) {
        errors.push('cardType 是必填参数')
      }
      if (!currentParams.title) {
        errors.push('title 是必填参数')
      }
      break
    case 'Card.ModifyContent':
      if (currentParams.contentMerge) {
        // 合并模式：检查 contentMerge 是否为有效对象
        if (!currentParams.contentMerge || typeof currentParams.contentMerge !== 'object') {
          errors.push('contentMerge 必须是有效的对象')
        }
      } else {
        // 路径模式：检查 setPath 是否存在
        if (!currentParams.setPath) {
          errors.push('路径模式下 setPath 是必填参数')
        }
      }
      break
    case 'Card.ClearFields':
      if (!currentParams.fields || !Array.isArray(currentParams.fields) || currentParams.fields.length === 0) {
        errors.push('fields 必须是非空数组')
      }
      break
  }
  
  return errors
})

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
// 针对"子卡内容键名"的建议：来自子卡类型 schema 的根部一级 keys
function extractContentKeys(schema: any): string[] {
  try {
    const props = (schema?.properties || {}) as Record<string, any>
    return Object.keys(props)
  } catch { return [] }
}

// 数组编辑辅助函数
function addField() {
  const fields = params.value.fields || []
  update('fields', [...fields, ''])
}

function removeField(index:string | number) {
  index=Number(index)
  const fields = [...(params.value.fields || [])]
  fields.splice(index, 1)
  update('fields', fields)
}

function updateFieldsArray() {
  // 触发响应式更新
  const fields = [...(params.value.fields || [])]
  update('fields', fields)
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

// Card.Read 节点增强功能
const selectedCardType = computed(() => {
  const typeName = params.value?.type_name
  return typeName ? state.types.find(t => t.name === typeName) : null
})

const parsedFields = ref<ParsedField[]>([])

// 监听卡片类型变化，重新解析字段
watch(selectedCardType, (newType) => {
  if (newType?.json_schema) {
    parsedFields.value = parseSchemaFields(newType.json_schema)
  } else {
    parsedFields.value = []
  }
}, { immediate: true })

function handleTypeChange(typeName: string) {
  update('type_name', typeName)
}

function handleFieldSelect(fieldPath: string) {
  // 复制字段路径到剪贴板
  if (navigator.clipboard) {
    navigator.clipboard.writeText(fieldPath).then(() => {
      ElMessage.success(`已复制路径: ${fieldPath}`)
    }).catch(() => {
      console.log(`已复制路径: ${fieldPath}`)
    })
  } else {
    console.log(`路径: ${fieldPath}`)
  }
}

function handleFieldToggle(fieldPath: string) {
  toggleFieldExpanded(parsedFields.value, fieldPath)
}

</script>

<template>
  <div class="panel" v-if="node">
    <div class="panel-title">参数 · {{ typeName }}</div>
    
    <!-- 错误提示 -->
    <div v-if="paramErrors.length > 0" class="error-alert">
      <el-alert 
        type="error" 
        :title="`参数错误 (${paramErrors.length})`" 
        :closable="false"
        show-icon
      >
        <ul class="error-list">
          <li v-for="error in paramErrors" :key="error">{{ error }}</li>
        </ul>
      </el-alert>
    </div>
    
    <!-- 智能建议 -->
    <div v-if="suggestions.length > 0" class="suggestions">
      <div class="suggestions-title">
        <el-icon><QuestionFilled /></el-icon>
        智能建议
      </div>
      <div class="suggestions-list">
        <div 
          v-for="(suggestion, index) in suggestions" 
          :key="index"
          class="suggestion-item"
          @click="applySuggestion(suggestion)"
        >
          <div class="suggestion-content">
            <code class="suggestion-key">{{ suggestion.key }}</code>
            <span class="suggestion-desc">{{ suggestion.description }}</span>
          </div>
          <el-button size="small" type="primary" plain>应用</el-button>
        </div>
      </div>
    </div>

    <!-- Card.Read（绑定卡片类型作为工作流上下文） -->
    <template v-if="typeName === 'Card.Read'">
      <el-form label-width="110px" size="small">
        <el-form-item label="目标卡片">
          <el-input :model-value="params.target || '$self'" @update:model-value="v=>update('target', v)" placeholder="$self" />
        </el-form-item>
        <el-form-item label="卡片类型">
          <el-select :model-value="params.type_name || selectedTypeName" @update:model-value="handleTypeChange" placeholder="请选择此工作流绑定的卡片类型" clearable>
            <el-option v-for="t in state.types" :key="t.id" :label="t.name" :value="t.name" />
          </el-select>
        </el-form-item>
        
        <!-- 字段结构展示 - 暂时注释等待 TypeScript 缓存问题解决
        <div v-if="selectedCardType && parsedFields.length > 0" class="field-structure">
          <div class="field-structure-title">
            <el-icon><DocumentCopy /></el-icon>
            字段结构
          </div>
          <div class="field-tree">
            <FieldTreeNode 
              v-for="field in parsedFields" 
              :key="field.path"
              :field="field"
              :level="0"
              @select-field="handleFieldSelect"
              @toggle-expand="handleFieldToggle"
            />
          </div>
        </div>
        -->
        
        <div class="tip">说明：选择卡片类型后可查看其字段结构，点击字段可复制路径。后续节点会使用该类型进行路径选择与校验。</div>
      </el-form>
    </template>

    <!-- List.ForEach -->
    <template v-else-if="typeName === 'List.ForEach'">
      <el-form label-width="110px" size="small">
        <el-form-item label="listPath">
          <div class="horiz">
            <el-input class="flex1" :model-value="params.listPath || params.list" @update:model-value="v=>update('listPath', v)" placeholder="如：$.content.xxx" />
            <el-select style="width: 180px" :model-value="params.listPath" @update:model-value="v=>update('listPath', v)" filterable clearable placeholder="选择字段">
              <el-option v-for="option in fieldPathOptions" :key="option.value" :label="option.label" :value="option.value" />
            </el-select>
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
        <!-- 当使用 item 作为内容时，允许额外通过 contentMerge 覆盖/补充字段 -->
        <el-form-item v-if="params.useItemAsContent" label="内容合并 (可选)">
          <el-input 
            type="textarea" 
            :rows="4" 
            :model-value="contentMergeText" 
            @update:model-value="updateContentMerge" 
            placeholder='JSON，如：{"title": "第{item.chapter_number}章 {item.title}"}'
          />
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
              <el-select style="width: 180px" :model-value="''" @update:model-value="v=>updateExprOrTemplate(v)" filterable clearable placeholder="插入字段">
                <el-option v-for="option in fieldPathOptions" :key="option.value" :label="option.label" :value="option.value" />
              </el-select>
            </div>
          </template>
        </el-form-item>
      </el-form>
    </template>

    <!-- Card.ModifyContent -->
    <template v-else-if="typeName === 'Card.ModifyContent'">
      <el-form label-width="110px" size="small">
        <!-- 上下文说明 -->
        <el-alert 
          title="作用目标：当前卡片 (state.card)" 
          description="此节点会修改由 Card.Read 节点读取的卡片，而不是连接线上游的卡片。" 
          type="info" 
          :closable="false" 
          show-icon
          style="margin-bottom: 16px;"
        />
        
        <!-- 模式选择 -->
        <el-form-item label="修改模式">
          <el-radio-group :model-value="modifyContentMode" @update:model-value="switchModifyContentMode">
            <el-radio value="path">路径设置</el-radio>
            <el-radio value="merge">内容合并</el-radio>
          </el-radio-group>
        </el-form-item>
        
        <!-- 路径设置模式 -->
        <template v-if="modifyContentMode === 'path'">
          <el-form-item label="setPath">
            <div class="horiz">
              <el-input class="flex1" :model-value="params.setPath" @update:model-value="v=>update('setPath', v)" placeholder="$.content.xxx" />
              <el-select style="width: 180px" :model-value="params.setPath" @update:model-value="v=>update('setPath', v)" filterable clearable placeholder="选择字段">
                <el-option v-for="option in fieldPathOptions" :key="option.value" :label="option.label" :value="option.value" />
              </el-select>
            </div>
          </el-form-item>
          <el-form-item label="setValue">
            <el-input :model-value="params.setValue" @update:model-value="v=>update('setValue', v)" placeholder="可用 {item.xxx}" />
          </el-form-item>
        </template>
        
        <!-- 内容合并模式 -->
        <template v-else>
          <el-form-item label="contentMerge">
            <el-input 
              type="textarea" 
              :rows="6" 
              :model-value="contentMergeText" 
              @update:model-value="updateContentMerge" 
              placeholder='JSON格式，如：{"field1": "value1", "field2": []}'
            />
          </el-form-item>
        </template>
      </el-form>
    </template>

    <!-- Card.ClearFields -->
    <template v-else-if="typeName === 'Card.ClearFields'">
      <el-form label-width="110px" size="small">
        <el-form-item label="目标卡片">
          <el-input v-model="params.target" placeholder="$self" />
        </el-form-item>
        <el-form-item label="清空字段">
          <div class="fields-editor">
            <div v-for="(field, index) in (params.fields || [])" :key="index" class="field-row">
              <el-input 
                v-model="params.fields[index]" 
                placeholder="$.content.field_name"
                @input="updateFieldsArray"
              />
              <el-button 
                size="small" 
                type="danger" 
                @click="removeField(index)"
                :icon="'Delete'"
              />
            </div>
            <el-button size="small" type="primary" @click="addField">添加字段</el-button>
          </div>
        </el-form-item>
      </el-form>
    </template>


    <template v-else>
      <div class="empty">暂不支持该节点的参数编辑</div>
    </template>
  </div>
</template>

<style scoped>
.panel { 
  padding: 8px; 
  border-left: 1px solid var(--el-border-color); 
  height: 60vh; 
  overflow: auto; 
  background: var(--el-bg-color); 
  color: var(--el-text-color-primary); 
}

/* 错误提示样式 */
.error-alert {
  margin-bottom: 16px;
}

.error-list {
  margin: 8px 0 0 0;
  padding-left: 16px;
}

.error-list li {
  margin-bottom: 4px;
  font-size: 13px;
}

/* 智能建议样式 */
.suggestions {
  margin-bottom: 20px;
  background: #f0f9ff;
  border: 1px solid #b3d8ff;
  border-radius: 6px;
  padding: 12px;
}

.suggestions-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 500;
  color: #1f2937;
  margin-bottom: 8px;
}

.suggestions-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.suggestion-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.suggestion-item:hover {
  border-color: #3b82f6;
  background: #fefefe;
}

.suggestion-content {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
}

.suggestion-key {
  font-size: 12px;
  color: #059669;
  background: #ecfdf5;
  padding: 2px 6px;
  border-radius: 3px;
  align-self: flex-start;
}

.suggestion-desc {
  font-size: 13px;
  color: #6b7280;
}

.suggestion-item .el-button {
  margin-left: 8px;
  opacity: 0.7;
}

.suggestion-item:hover .el-button {
  opacity: 1;
}

/* 数组编辑器样式 */
.fields-editor {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.field-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.field-row .el-input {
  flex: 1;
}

/* 字段结构样式 */
.field-structure {
  margin-top: 12px;
  border: 1px solid var(--el-border-color-light, #e4e7ed);
  border-radius: 6px;
  background: var(--el-bg-color-page, #fafafa);
  overflow: hidden;
}

.field-structure-title {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 8px;
  background: var(--el-color-primary-light-9, #f0f9ff);
  border-bottom: 1px solid var(--el-border-color-lighter, #ebeef5);
  font-weight: 500;
  color: var(--el-text-color-primary, #303133);
  font-size: 12px;
}

.field-tree {
  padding: 4px 6px;
  max-height: 350px;
  overflow-y: auto;
  font-size: 11px;
}

/* 优化滚动条样式 */
.field-tree::-webkit-scrollbar {
  width: 6px;
}

.field-tree::-webkit-scrollbar-track {
  background: var(--el-border-color-extra-light, #f2f6fc);
  border-radius: 3px;
}

.field-tree::-webkit-scrollbar-thumb {
  background: var(--el-border-color, #dcdfe6);
  border-radius: 3px;
}

.field-tree::-webkit-scrollbar-thumb:hover {
  background: var(--el-text-color-secondary, #909399);
}

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


