<template>
  <div class="generic-card-editor">
    <EditorHeader
      :project-name="projectName"
      :card-type="props.card.card_type.name"
      v-model:title="titleProxy"
      :dirty="isDirty"
      :saving="isSaving"
      :can-save="isDirty && !isSaving"
      :last-saved-at="lastSavedAt"
      @save="handleSave"
      @generate="handleGenerate"
      @open-context="openDrawer = true"
      @delete="handleDelete"
      @open-versions="showVersions = true"
    />

    <!-- 参数卡区域：紧凑化布局 + 单行摘要（带省略与气泡提示）；工具条靠右对齐 -->
    <div class="toolbar-row param-toolbar">
      <div class="param-inline">
        <!-- 去掉 clearable，避免出现 X 清除按钮；保留可搜索 -->
        <el-select v-model="selectedAiParamCardId" placeholder="选择参数卡" class="param-select-top" @change="onParamChange" filterable>
          <el-option v-for="p in paramCards" :key="p.id" :label="p.name || ('参数卡 ' + p.id)" :value="p.id" />
        </el-select>
        <el-tooltip placement="top" :content="paramFullText">
          <el-tag size="small" effect="plain" class="param-summary">{{ paramShortText }}</el-tag>
        </el-tooltip>
        <el-button v-if="props.card.card_type.name === '章节正文' && projectStore.currentProject?.id" size="small" @click="openStudio">专注创作</el-button>
      </div>
    </div>

    <div class="editor-body">
      <div class="main-pane">
        <div v-if="schema" class="form-container">
          <template v-if="sections && sections.length">
            <SectionedForm v-if="wrapperName" :schema="innerSchema" v-model="innerData" :sections="sections" />
            <SectionedForm v-else :schema="schema" v-model="localData" :sections="sections" />
          </template>
          <template v-else>
            <ModelDrivenForm v-if="wrapperName" :schema="innerSchema" v-model="innerData" />
            <ModelDrivenForm v-else :schema="schema" v-model="localData" />
          </template>
        </div>
        <div v-else class="loading-or-error-container">
          <p v-if="schemaIsLoading">正在加载模型...</p>
          <p v-else>无法加载此卡片内容的编辑模型。</p>
        </div>
      </div>
    </div>

    <ContextDrawer
      v-model="openDrawer"
      :context-template="localAiContextTemplate"
      :preview-text="previewText"
      @apply-context="applyContextTemplateAndSave"
      @open-selector="openSelectorFromDrawer"
    >
      <template #params>
        <div class="param-placeholder">参数卡设置入口（保留原有逻辑）</div>
      </template>
    </ContextDrawer>

    <CardReferenceSelectorDialog v-model="isSelectorVisible" :cards="cards" :currentCardId="props.card.id" @confirm="handleReferenceConfirm" />
    <CardVersionsDialog
      v-if="projectStore.currentProject?.id"
      v-model="showVersions"
      :project-id="projectStore.currentProject!.id"
      :card-id="props.card.id"
      :current-content="wrapperName ? innerData : localData"
      :current-context-template="localAiContextTemplate"
      @restore="handleRestoreVersion"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { storeToRefs } from 'pinia'
import { useCardStore } from '@renderer/stores/useCardStore'
import { useAIStore } from '@renderer/stores/useAIStore'
import { useAIParamCardStore } from '@renderer/stores/useAIParamCardStore'
import { useProjectStore } from '@renderer/stores/useProjectStore'
import { schemaService } from '@renderer/api/schema'
import type { JSONSchema } from '@renderer/api/schema'
import ModelDrivenForm from '../dynamic-form/ModelDrivenForm.vue'
import SectionedForm from '../dynamic-form/SectionedForm.vue'
import { mergeSections, autoGroup, type SectionConfig } from '@renderer/services/uiLayoutService'
import CardReferenceSelectorDialog from './CardReferenceSelectorDialog.vue'
import EditorHeader from '../common/EditorHeader.vue'
import ContextDrawer from '../common/ContextDrawer.vue'
import { cloneDeep, isEqual } from 'lodash-es'
import type { CardRead, CardUpdate } from '@renderer/api/cards'
import { ElMessage, ElMessageBox } from 'element-plus'
import { addVersion, latestVersion } from '@renderer/services/versionService'
import CardVersionsDialog from '../common/CardVersionsDialog.vue'

const props = defineProps<{ card: CardRead }>()

const cardStore = useCardStore()
const aiStore = useAIStore()
const aiParamCardStore = useAIParamCardStore()
const projectStore = useProjectStore()

const { cards } = storeToRefs(cardStore)

const { paramCards } = storeToRefs(aiParamCardStore)

const openDrawer = ref(false)
const isSelectorVisible = ref(false)
const showVersions = ref(false)

const isSaving = ref(false)
const localData = ref<any>({})
const localAiContextTemplate = ref<string>('')
const originalData = ref<any>({})
const originalAiContextTemplate = ref<string>('')
const schema = ref<JSONSchema | undefined>(undefined)
const schemaIsLoading = ref(false)
const selectedAiParamCardId = ref<string | undefined>(undefined)
let atIndexForInsertion = -1
const sections = ref<SectionConfig[] | undefined>(undefined)
const wrapperName = ref<string | undefined>(undefined)
const innerSchema = ref<JSONSchema | undefined>(undefined)
const innerData = computed({
  get: () => {
    if (!wrapperName.value) return localData.value
    return (localData.value && localData.value[wrapperName.value]) || {}
  },
  set: (v: any) => {
    if (!wrapperName.value) { localData.value = v; return }
    localData.value = { ...(localData.value || {}), [wrapperName.value]: v }
  }
})

const projectName = '当前项目'
const lastSavedAt = ref<string | undefined>(undefined)
const titleProxy = ref(props.card.title)
watch(() => props.card.title, v => titleProxy.value = v)
watch(titleProxy, v => localData.value = { ...localData.value, title: v })

const isDirty = computed(() => {
  return !isEqual(localData.value, originalData.value) || localAiContextTemplate.value !== originalAiContextTemplate.value
})

watch(
  () => props.card,
  async (newCard) => {
    if (newCard) {
      localData.value = cloneDeep(newCard.content) || {}
      localAiContextTemplate.value = newCard.ai_context_template || ''
      originalData.value = cloneDeep(newCard.content) || {}
      originalAiContextTemplate.value = newCard.ai_context_template || ''
      titleProxy.value = newCard.title
      await loadSchemaForCard(newCard)
      selectedAiParamCardId.value = newCard.selected_ai_param_card_id ?? selectedAiParamCardId.value
    }
  },
  { immediate: true, deep: true }
)

const activeParam = computed(() => aiParamCardStore.findByKey?.(selectedAiParamCardId.value))

// 基于当前选择构造简短/完整的摘要文本（中文）
const paramShortText = computed(() => {
  const p = activeParam.value
  if (!p) return '未选择参数卡'
  const model = p.llm_config_id ? `模型:${p.llm_config_id}` : '模型:未设'
  const prompt = p.prompt_name ? `任务:${p.prompt_name}` : '任务:未设'
  return `${model} · ${prompt}`
})
const paramFullText = computed(() => {
  const p = activeParam.value
  if (!p) return '未选择参数卡'
  return `模型: ${p.llm_config_id ?? '未设置'} · 任务: ${p.prompt_name ?? '未设置'} · 响应模型: ${p.response_model_name ?? '未设置'} · 温度: ${p.temperature ?? '-'} · 最大tokens: ${p.max_tokens ?? '-'}`
})

function onParamChange() {
  // 当用户切换参数卡时，立即回写后端进行持久化
  // 仅更新 selected_ai_param_card_id 字段，不触发内容变更
  cardStore.modifyCard(props.card.id, { selected_ai_param_card_id: selectedAiParamCardId.value } as any, { skipHooks: true })
}

async function loadSchemaForCard(card: CardRead) {
  const outputModelName = (card.card_type as any).output_model_name as string | undefined
  schemaIsLoading.value = true
  try {
    await schemaService.loadSchemas()
    if (!outputModelName) {
      schema.value = undefined
      sections.value = undefined
      wrapperName.value = undefined
      innerSchema.value = undefined
      return
    }
    schema.value = schemaService.getSchema(outputModelName)
    // 若首次未命中（可能是刚新增的模型），尝试强制刷新一次
    if (!schema.value) {
      await schemaService.refreshSchemas()
      schema.value = schemaService.getSchema(outputModelName)
    }
    const props: any = (schema.value as any)?.properties || {}
    const keys = Object.keys(props)
    const onlyKey = keys.length === 1 ? keys[0] : undefined
    const isObject = onlyKey && (props[onlyKey]?.type === 'object' || props[onlyKey]?.$ref || props[onlyKey]?.anyOf)
    if (onlyKey && isObject) {
      wrapperName.value = onlyKey
      // 若包装字段为 $ref，则解引用以便正确渲染其 properties
      const maybeRef = props[onlyKey]
      if (maybeRef && typeof maybeRef === 'object' && '$ref' in maybeRef && typeof maybeRef.$ref === 'string') {
        const refName = maybeRef.$ref.split('/').pop() || ''
        innerSchema.value = schemaService.getSchema(refName) || maybeRef
      } else {
        innerSchema.value = maybeRef
      }
    } else {
      wrapperName.value = undefined
      innerSchema.value = undefined
    }
    const schemaForLayout = (wrapperName.value ? innerSchema.value : schema.value) as any
    const schemaMeta = schemaForLayout?.['x-ui'] || undefined
    const sectionsCfg = mergeSections({ schemaMeta, backendLayout: (card.card_type as any).ui_layout, frontendDefault: undefined })
    sections.value = sectionsCfg || autoGroup(schemaForLayout!)
  } finally {
    schemaIsLoading.value = false
  }
}

function handleReferenceConfirm(reference: string) {
  if (atIndexForInsertion < 0) {
    // 若未通过 @ 触发，则直接在末尾追加
    localAiContextTemplate.value = `${localAiContextTemplate.value}${reference}`
    ElMessage.success('已插入引用')
    return
  }
  const text = localAiContextTemplate.value
  const isAt = text.charAt(atIndexForInsertion) === '@'
  const before = text.substring(0, atIndexForInsertion)
  const after = text.substring(atIndexForInsertion + (isAt ? 1 : 0))
  localAiContextTemplate.value = before + reference + after
  atIndexForInsertion = -1
  ElMessage.success('已插入引用')
}

function applyContextTemplate(text: string) {
  localAiContextTemplate.value = text
}

async function applyContextTemplateAndSave(text: string) {
  localAiContextTemplate.value = typeof text === 'string' ? text : String(text)
  ElMessage.success('上下文模板已应用')
  openDrawer.value = false
  await handleSave()
}

// Alt+K 打开抽屉
function keyHandler(e: KeyboardEvent) {
  if ((e.altKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) {
    e.preventDefault()
    openDrawer.value = true
  }
}

onMounted(() => { window.addEventListener('keydown', keyHandler) })
onBeforeUnmount(() => { window.removeEventListener('keydown', keyHandler) })

// 在抽屉中输入 @ 时弹出选择器
let drawerTextarea: HTMLTextAreaElement | null = null
watch(() => openDrawer.value, (v) => {
  if (v) {
    nextTick(() => {
      drawerTextarea = document.querySelector('.context-area textarea') as HTMLTextAreaElement | null
      drawerTextarea?.addEventListener('input', handleDrawerInput)
    })
  } else {
    drawerTextarea?.removeEventListener('input', handleDrawerInput)
    drawerTextarea = null
    atIndexForInsertion = -1
  }
})

function handleDrawerInput(ev: Event) {
  const textarea = ev.target as HTMLTextAreaElement
  // 同步抽屉内文本到本地模板，避免选择器插入时丢失前缀
  localAiContextTemplate.value = textarea.value
  const cursorPos = textarea.selectionStart
  const lastChar = textarea.value.substring(cursorPos - 1, cursorPos)
  if (lastChar === '@') {
    atIndexForInsertion = cursorPos - 1
    isSelectorVisible.value = true
  }
}

function openSelectorFromDrawer() {
  const textarea = document.querySelector('.context-area textarea') as HTMLTextAreaElement | null
  if (textarea) {
    localAiContextTemplate.value = textarea.value
    // 在光标当前位置插入，不回退一位
    atIndexForInsertion = textarea.selectionStart
  }
  isSelectorVisible.value = true
}

const previewText = computed(() => localAiContextTemplate.value)

async function handleSave() {
  isSaving.value = true
  const payload: CardUpdate = {
    content: localData.value,
    ai_context_template: localAiContextTemplate.value,
    selected_ai_param_card_id: selectedAiParamCardId.value
  }
  try {
    await cardStore.modifyCard(props.card.id, payload)
    // 保存快照到本地版本库（仅当有实质变化时）
    if (projectStore.currentProject?.id) {
      const pid = projectStore.currentProject.id
      const latest = latestVersion(pid, props.card.id)
      const newContent = wrapperName.value ? innerData.value : localData.value
      const newCtx = localAiContextTemplate.value || ''
      const sameContent = latest ? JSON.stringify(latest.content ?? {}) === JSON.stringify(newContent ?? {}) : false
      const sameCtx = latest ? String(latest.ai_context_template ?? '') === String(newCtx) : false
      if (!(sameContent && sameCtx)) {
        addVersion(pid, {
          cardId: props.card.id,
          projectId: pid,
          title: props.card.title,
          content: newContent,
          ai_context_template: newCtx,
        })
      }
    }
    originalData.value = cloneDeep(localData.value)
    originalAiContextTemplate.value = localAiContextTemplate.value
    lastSavedAt.value = new Date().toLocaleTimeString()
    ElMessage.success('保存成功！')
  } finally { isSaving.value = false }
}

async function handleDelete() {
  try {
    await ElMessageBox.confirm(`确认删除卡片「${props.card.title}」？此操作不可恢复`, '删除确认', { type: 'warning' })
    await cardStore.removeCard(props.card.id)
    ElMessage.success('卡片已删除')
    // 返回到卡片集市
    const evt = new CustomEvent('nf:navigate', { detail: { to: 'market' } })
    window.dispatchEvent(evt)
  } catch (e) {
    // 用户取消或失败
  }
}

async function handleGenerate() {
  const outputModelName = (props.card.card_type as any).output_model_name as string | undefined
  if (!outputModelName) { ElMessage.error('此卡片类型未配置输出模型。'); return }
  const selectedParamCard = aiParamCardStore.findByKey(selectedAiParamCardId.value)
  if (!selectedParamCard || !selectedParamCard.llm_config_id) { ElMessage.error('请先选择一个有效的AI参数配置。'); return }
  const { resolveTemplate } = await import('@renderer/services/contextResolver')
  // 关键修复：用“当前编辑态”的内容参与解析（未保存也生效）
  const editingContent = wrapperName.value ? innerData.value : localData.value
  const currentCardForResolve = { ...props.card, content: editingContent }
  const resolvedContext = resolveTemplate({ template: localAiContextTemplate.value, cards: cards.value, currentCard: currentCardForResolve as any })
  try {
    const result = await aiStore.generateContent(String(outputModelName), resolvedContext, selectedParamCard.llm_config_id, selectedParamCard.prompt_name ?? undefined)
    if (result) { localData.value = result; ElMessage.success('内容生成成功！') }
  } catch (e) { console.error('AI generation failed:', e) }
}

async function handleRestoreVersion(v: any) {
  // 恢复版本内容并保存
  if (wrapperName.value) innerData.value = v.content
  else localData.value = v.content
  localAiContextTemplate.value = v.ai_context_template || localAiContextTemplate.value
  showVersions.value = false
  ElMessage.success('已恢复版本，自动保存中...')
  await handleSave()
}

function openStudio() {
  const pid = projectStore.currentProject?.id
  if (!pid) return
  // @ts-ignore
  window.api?.openChapterStudio?.(pid, props.card.id)
}
</script>

<style scoped>
.generic-card-editor { display: flex; flex-direction: column; height: 100%; }
.editor-body { display: grid; grid-template-columns: 1fr; gap: 0; flex: 1; overflow: hidden; }
.main-pane { overflow: auto; padding: 12px; }
.form-container { display: flex; flex-direction: column; gap: 12px; }
.loading-or-error-container { text-align: center; padding: 2rem; color: var(--el-text-color-secondary); }
.toolbar-row { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-bottom: 1px solid var(--el-border-color-light); }
.param-select-top { min-width: 220px; }
.param-hint { color: var(--el-text-color-secondary); font-size: 12px; }
/* 工具条靠右对齐，使参数条目不与主标题区域抢占注意力 */
.param-toolbar { padding: 6px 12px; border-bottom: 1px solid var(--el-border-color-light); justify-content: flex-end; }
.param-inline { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
/* 选择器宽度适中，避免占满整行 */
.param-select-top { width: 240px; max-width: 50vw; }
/* 摘要标签单行省略，随容器自适应 */
.param-summary { max-width: 48vw; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

@media (max-width: 1024px) {
  .param-select-top { width: 200px; }
  .param-summary { max-width: 40vw; }
}
@media (max-width: 640px) {
  .param-select-top { width: 180px; }
  .param-summary { max-width: 60vw; }
}
</style> 