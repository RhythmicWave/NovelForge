<template>
  <div class="studio-layout">
    <div class="studio-header">
      <div class="left">
        <h3>Chapter Studio</h3>
        <el-tag v-if="chapterCard" size="small">{{ chapterCard.title }}</el-tag>
      </div>
    </div>

    <div class="studio-body">
      <div class="editor-pane">
        <component :is="CodeMirrorEditor" 
                   v-if="chapterCard"
                   :card="chapterCard"
                   :chapter="chapterModel"
                   :prefetched="prefetchedContext"
                   @update:chapter="onChapterModelChange"
                   @save="onSave"
                   :context-params="({ project_id: projectId || undefined, volume_number: chapterModel.volume_number || undefined, chapter_number: chapterModel.chapter_number || undefined, extra_context_fn: getStoryOutlineText, stage_overview: (currentStageLine && currentStageLine.overview) || undefined } as any)" />
        <div v-else class="placeholder">未找到章节卡片</div>
      </div>
      <div class="right-pane">
        <el-tabs v-model="activeTab" type="border-card" class="right-tabs">
          <el-tab-pane label="写作上下文" name="context">
            <ContextPanel :project-id="projectId || undefined"
                          :participants="participants"
                          :volume-number="chapterModel.volume_number ?? null"
                          :stage-number="chapterModel.stage_number ?? null"
                          :chapter-number="chapterModel.chapter_number ?? null"
                          :prefetched="prefetchedContext"
                          @update:participants="onParticipantsChange"
                          @update:volumeNumber="onVolumeChange"
                          @update:stageNumber="onStageChange"
                          @update:chapterNumber="onChapterChange"
                          :draft-tail="''"/>
          </el-tab-pane>
          <el-tab-pane label="大纲速查" name="outline">
            <OutlinePanel :outline="currentVolumeOutline"
                          :current-stage="currentStageLine"
                          :volume-number="chapterModel.volume_number ?? null"
                          :chapter-number="chapterModel.chapter_number ?? null" />
          </el-tab-pane>
          <el-tab-pane label="智能工具" name="tools">
            <div class="panel-pad">
              <h4>动态信息提取</h4>
              <el-form label-width="100px">
                <el-form-item label="LLM配置">
                  <el-select v-model="llmConfigIdForExtract" placeholder="选择模型" filterable style="width: 260px">
                    <el-option v-for="cfg in llmOptions" :key="cfg.id" :label="cfg.display_name || ('配置 ' + cfg.id)" :value="cfg.id" />
                  </el-select>
                </el-form-item>
                <el-form-item label="预览后更新">
                  <el-switch v-model="previewBeforeUpdate" />
                </el-form-item>
                <el-form-item>
                  <el-button type="warning" @click="onTriggerExtract">提取动态信息</el-button>
                </el-form-item>
              </el-form>
            </div>
          </el-tab-pane>
        </el-tabs>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, defineAsyncComponent } from 'vue'
import { useRouteHashQuery } from '@renderer/utils/useRouteHashQuery'
import type { CardRead, CardUpdate } from '@renderer/api/cards'
import { ElMessage } from 'element-plus'
import { useCardStore } from '@renderer/stores/useCardStore'
import { storeToRefs } from 'pinia'
import { useEditorStore } from '@renderer/stores/useEditorStore'
import { getAIConfigOptions, type AIConfigOptions } from '@renderer/api/ai'

const CodeMirrorEditor = defineAsyncComponent(() => import('@renderer/components/editors/CodeMirrorEditor.vue'))
const ContextPanel = defineAsyncComponent(() => import('@renderer/components/panels/ContextPanel.vue'))
const OutlinePanel = defineAsyncComponent(() => import('@renderer/components/panels/OutlinePanel.vue'))

type ContextParams = { project_id?: number; volume_number?: number; chapter_number?: number; participants?: string[]; extra_context_fn?: Function; [key: string]: any }

const activeTab = ref('context')
const projectId = ref<number | null>(null)
const cardId = ref<number | null>(null)
const chapterCard = ref<CardRead | null>(null)

const cardStore = useCardStore()
const { cards } = storeToRefs(cardStore)
const editorStore = useEditorStore()
const llmConfigIdForExtract = ref<number | null>(null)
const previewBeforeUpdate = ref(true)
const llmOptions = ref<Array<{ id: number; display_name: string }>>([])

// 当前分卷大纲（右侧速查）
const currentVolumeOutline = ref<any | null>(null)

// 父组件统一维护的 Chapter 模型
const chapterModel = ref<{ title?: string; volume_number?: number; stage_number?: number; chapter_number?: number; entity_list?: Array<string|{name:string}>; content: string }>({ content: '' })
const participants = ref<string[]>([])
const prefetchedContext = ref<any | null>(null)
const currentStageLine = ref<any | null>(null)

function onChapterModelChange(val: any) {
  chapterModel.value = { ...chapterModel.value, ...(val || {}) }
  // 同步参与者
  try {
    const list: any[] = (chapterModel.value.entity_list as any[]) || []
    participants.value = Array.isArray(list) ? list.map((x:any) => typeof x === 'string' ? x : (x?.name || '')).filter(Boolean).slice(0, 6) : []
  } catch { participants.value = [] }
}

function onParticipantsChange(list: string[]) {
  participants.value = Array.isArray(list) ? list.filter(Boolean) : []
  chapterModel.value.entity_list = [...participants.value]
}

function onVolumeChange(v: number | null) {
  chapterModel.value.volume_number = (v == null ? undefined : v)
}

function onStageChange(v: number | null) {
  chapterModel.value.stage_number = (v == null ? undefined : v)
}

function onChapterChange(v: number | null) {
  chapterModel.value.chapter_number = (v == null ? undefined : v)
}

async function onSave() {
  if (!projectId.value || !chapterCard.value) return
  const updatePayload: CardUpdate = {
    title: chapterCard.value.title,
    content: {
      ...(chapterCard.value.content as any || {}),
      // 将父组件的 Chapter 模型写回卡片内容
      title: chapterModel.value.title ?? chapterCard.value.title,
      volume_number: chapterModel.value.volume_number,
      chapter_number: chapterModel.value.chapter_number,
      entity_list: chapterModel.value.entity_list || [],
      content: chapterModel.value.content || ''
    }
  }
  try {
    await cardStore.modifyCard(chapterCard.value.id, updatePayload)
    ElMessage.success('章节已保存')
  } catch {
    ElMessage.error('保存失败')
  }
}

// 进入卡片后自动装配一次上下文，用于右侧预览
async function preAssembleContextIfPossible() {
  try {
    const projectId = projectIdRef()
    if (!projectId) return
    const vol = chapterModel.value.volume_number
    const ch = chapterModel.value.chapter_number
    const parts = participants.value
    const { assembleContext } = await import('@renderer/api/ai')
    const res = await assembleContext({ project_id: projectId, volume_number: vol, chapter_number: ch, participants: parts, current_draft_tail: '' })
    prefetchedContext.value = res
  } catch {}
}

function projectIdRef() { return projectId.value || null }

// 组装“主线/支线”大纲文本（保留）
function getStoryOutlineText() {
  const o: any = currentVolumeOutline.value || {}
  const lines: string[] = []
  try {
    if (o?.main_target) {
      const name = o.main_target.name || ''
      const overview = o.main_target.overview || ''
      lines.push(`【主线】${name}\n${overview}`)
    }
    if (Array.isArray(o?.branch_line) && o.branch_line.length) {
      lines.push('【支线】')
      o.branch_line.forEach((b: any, i: number) => {
        const n = b?.name || `支线${i+1}`
        const over = b?.overview || ''
        lines.push(`- ${n}：${over}`)
      })
    }
  } catch {}
  return lines.join('\n')
}

function findVolumeOutline(card:CardRead|null){
  if(card){
    if(card.parent_id){
      const parent_id=card.parent_id
      const parent = cards.value?.find(c => c.id === parent_id)
      if(parent){
        if(parent.card_type?.name === '分卷大纲'){
          currentVolumeOutline.value = parent.content
          // 若当前阶段号未设置，则根据章节号匹配所处阶段
          try {
            const stageLines: any[] = Array.isArray((parent.content as any)?.stage_lines) ? (parent.content as any).stage_lines : []
            const chNo = chapterModel.value.chapter_number
            if (typeof chNo === 'number') {
              currentStageLine.value = stageLines.find(st => Array.isArray(st.reference_chapter) && st.reference_chapter.length === 2 && chNo >= st.reference_chapter[0] && chNo <= st.reference_chapter[1]) || null
              if (currentStageLine.value && chapterModel.value.stage_number == null) {
                const idx = Number(currentStageLine.value.stage_number || stageLines.indexOf(currentStageLine.value) + 1)
                chapterModel.value.stage_number = idx
              }
            }
          } catch {}
          // 注入卷号（若章节模型未设置）
          const volNum = (parent.content as any)?.volume_number
          if (chapterModel.value.volume_number == null && typeof volNum === 'number') chapterModel.value.volume_number = volNum
          // 若当前章节模型未设置参与者且父为章节大纲，尝试注入参与者
          try {
            const co: any = parent.content || {}
            if (!Array.isArray(chapterModel.value.entity_list) || chapterModel.value.entity_list.length === 0) {
              const raw = (co.character_list || co.entity_list || []) as any[]
              const names = raw.map((x:any) => typeof x === 'string' ? x : (x?.name || '')).filter((s:string) => !!s)
              if (names.length) { onParticipantsChange(names.slice(0,6)) }
            }
          } catch {}
        }else{
          findVolumeOutline(parent)
        }
      }
    }
  }
}

onMounted(async () => {
  const q = useRouteHashQuery()
  projectId.value = Number(q.projectId || 0) || null
  cardId.value = Number(q.cardId || 0) || null
  if (!projectId.value || !cardId.value) {
    ElMessage.error('缺少必要参数 projectId/cardId')
    return
  }
  try {
    await cardStore.fetchCards(projectId.value)
    chapterCard.value = (cards.value || []).find(c => c.id === cardId.value) || null
    if (chapterCard.value) cardStore.setActiveCard(chapterCard.value.id)
    if (!chapterCard.value) { ElMessage.error('未找到章节卡片'); return }
    // 初始化 chapterModel
    const cc: any = chapterCard.value.content || {}
    chapterModel.value = {
      title: cc.title ?? chapterCard.value.title,
      volume_number: cc.volume_number ?? undefined,
      stage_number: cc.stage_number ?? undefined,
      chapter_number: cc.chapter_number ?? undefined,
      entity_list: Array.isArray(cc.entity_list) ? cc.entity_list : [],
      content: typeof cc.content === 'string' ? cc.content : ''
    }
    onChapterModelChange(chapterModel.value)
    findVolumeOutline(chapterCard.value)
    // 若仍未注入参与者，尝试从直接父卡（章节大纲）读取
    try {
      if (participants.value.length === 0 && chapterCard.value.parent_id) {
        const parent = (cards.value || []).find(c => c.id === chapterCard.value?.parent_id)
        const pco: any = parent?.content || {}
        const raw = (pco.character_list || pco.entity_list || []) as any[]
        const names = raw.map((x:any) => typeof x === 'string' ? x : (x?.name || '')).filter((s:string) => !!s)
        if (names.length) onParticipantsChange(names.slice(0,6))
        const chNo = typeof pco.chapter_number === 'number' ? pco.chapter_number : undefined
        if (chapterModel.value.chapter_number == null && chNo != null) chapterModel.value.chapter_number = chNo
      }
    } catch {}
    // 自动装配一次上下文
    await preAssembleContextIfPossible()
    // 加载 LLM 配置选项
    try {
      const opts: AIConfigOptions = await getAIConfigOptions()
      llmOptions.value = (opts.llm_configs || []) as any
      if (!llmConfigIdForExtract.value && llmOptions.value.length) {
        llmConfigIdForExtract.value = llmOptions.value[0].id
      }
    } catch {}
  } catch (e) {
    ElMessage.error('加载章节失败')
  }
})

async function onTriggerExtract() {
  try {
    await editorStore.triggerExtractDynamicInfo({ llm_config_id: llmConfigIdForExtract.value || undefined, preview: previewBeforeUpdate.value })
  } catch (e) {}
}
</script>

<style scoped>
.studio-layout { display: flex; flex-direction: column; height: 100vh; }
.studio-header { display: flex; justify-content: space-between; align-items: center; padding: 8px 12px; border-bottom: 1px solid var(--el-border-color-light); background: var(--el-bg-color); }
.studio-body { flex: 1; display: grid; grid-template-columns: 1fr 360px; height: calc(100vh - 75px); }
.editor-pane { min-height: 0; overflow: hidden; }
.right-pane { border-left: 1px solid var(--el-border-color-light); overflow: hidden; }
.right-tabs { height: 100%; display: flex; flex-direction: column; }
:deep(.el-tabs__content) { flex: 1; overflow: auto; }
.placeholder { display: flex; align-items: center; justify-content: center; height: 100%; color: var(--el-text-color-secondary); }
.panel-pad { padding: 10px; color: var(--el-text-color-regular); }
</style> 