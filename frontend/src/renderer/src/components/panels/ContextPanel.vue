<template>
  <div class="ctx-panel">
    <el-form label-width="90px" class="controls">
      <el-form-item label="卷号">
        <el-input-number v-model="localVolumeNumber" :min="0" :max="999" @change="emitVolume" />
      </el-form-item>
      <el-form-item label="章节号">
        <el-input-number v-model="localChapterNumber" :min="1" :max="9999" @change="emitChapter" />
      </el-form-item>
      <el-form-item label="参与者">
        <el-select v-model="localParticipants" multiple filterable allow-create default-first-option placeholder="输入或选择参与者" @change="emitParticipants">
          <el-option v-for="p in participantOptions" :key="p" :label="p" :value="p" />
        </el-select>
      </el-form-item>
      <div class="actions">
        <el-button size="small" type="primary" :loading="assembling" @click="assemble">注入知识图谱</el-button>
      </div>
    </el-form>

    <div v-if="assembled" class="assembled">
      <div class="facts-structured" v-if="assembled.facts_structured">
        <div class="facts-title" v-if="Array.isArray((assembled.facts_structured as any)?.fact_summaries) && ((assembled.facts_structured as any)?.fact_summaries?.length > 0)">关键事实</div>
        <ul class="list" v-if="Array.isArray((assembled.facts_structured as any)?.fact_summaries) && ((assembled.facts_structured as any)?.fact_summaries?.length > 0)">
          <li v-for="(f, i0) in ((assembled.facts_structured as any)?.fact_summaries as string[] || [])" :key="i0">- {{ f }}</li>
        </ul>

        <div class="facts-title" v-if="Array.isArray((assembled.facts_structured as any)?.relation_summaries) && ((assembled.facts_structured as any)?.relation_summaries?.length > 0)">关系摘要</div>
        <ul class="list" v-if="Array.isArray((assembled.facts_structured as any)?.relation_summaries) && ((assembled.facts_structured as any)?.relation_summaries?.length > 0)">
          <li v-for="(r, idx) in ((assembled.facts_structured as any)?.relation_summaries as any[] || [])" :key="idx" class="relation-item">
            <div class="relation-head">{{ (r as any).a }} ↔ {{ (r as any).b }}（{{ (r as any).kind }}）</div>
            <div v-if="(r as any).a_to_b_addressing || (r as any).b_to_a_addressing" class="muted addressing">
              <span v-if="(r as any).a_to_b_addressing">A称B：{{ (r as any).a_to_b_addressing }}</span>
              <span v-if="(r as any).b_to_a_addressing" style="margin-left:12px;">B称A：{{ (r as any).b_to_a_addressing }}</span>
            </div>
            <div v-if="Array.isArray((r as any)?.recent_dialogues) && ((r as any).recent_dialogues?.length > 0)" class="muted">
              对话样例：
              <ul class="list">
                <li v-for="(d, i3) in ((r as any).recent_dialogues as string[] || [])" :key="i3"><div class="dialog-text">{{ d }}</div></li>
              </ul>
            </div>
            <div v-if="Array.isArray((r as any)?.recent_event_summaries) && ((r as any).recent_event_summaries?.length > 0)" class="muted">
              近期事件：
              <ul class="list">
                <li v-for="(ev, i4) in ((r as any).recent_event_summaries as any[] || [])" :key="i4">
                  <span>{{ (ev as any).summary }}</span>
                  <span class="badges" v-if="(ev as any).volume_number != null || (ev as any).chapter_number != null">
                    <el-tag size="small" type="info" v-if="(ev as any).volume_number != null">卷{{ (ev as any).volume_number }}</el-tag>
                    <el-tag size="small" type="info" v-if="(ev as any).chapter_number != null" style="margin-left:6px;">章{{ (ev as any).chapter_number }}</el-tag>
                  </span>
                </li>
              </ul>
            </div>
          </li>
        </ul>
        <div class="raw-toggle">
          <el-button text type="primary" size="small" @click="showRaw = !showRaw">{{ showRaw ? '隐藏文本回显' : '查看文本回显' }}</el-button>
        </div>
      </div>
      <pre class="pre" v-if="!assembled.facts_structured || showRaw">{{ assembled.facts_subgraph }}</pre>
      <div class="budget" v-if="assembled.budget_stats">
        <span>总长：{{ assembled.budget_stats.total }} / 软阈 {{ assembled.budget_stats.soft_budget }} / 硬上限 {{ assembled.budget_stats.hard_budget }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { assembleContext, type AssembleContextResponse } from '@renderer/api/ai'
import { ElMessage } from 'element-plus'
import { getCardsForProject, type CardRead } from '@renderer/api/cards'

const props = defineProps<{ projectId?: number; participants?: string[]; volumeNumber?: number | null; chapterNumber?: number | null; draftTail?: string; prefetched?: AssembleContextResponse | null }>()
const emit = defineEmits<{ (e:'update:participants', v: string[]): void; (e:'update:volumeNumber', v: number | null): void; (e:'update:chapterNumber', v: number | null): void }>()

const assembling = ref(false)
const assembled = ref<AssembleContextResponse | null>(null)
const showRaw = ref(false)

const participantOptions = ref<string[]>([])
const localParticipants = ref<string[]>(props.participants || [])
const localVolumeNumber = ref<number | null>(props.volumeNumber ?? null)
const localChapterNumber = ref<number | null>(props.chapterNumber ?? null)

watch(() => props.participants, (v) => { localParticipants.value = [...(v || [])] })
watch(() => props.volumeNumber, (v) => { localVolumeNumber.value = v ?? null })
watch(() => props.chapterNumber, (v) => { localChapterNumber.value = v ?? null })
watch(() => props.prefetched, (v) => { if (v) assembled.value = v })

function emitParticipants() { emit('update:participants', [...localParticipants.value]) }
function emitVolume() { emit('update:volumeNumber', localVolumeNumber.value ?? null) }
function emitChapter() { emit('update:chapterNumber', localChapterNumber.value ?? null) }

async function loadParticipantOptions() {
  if (!props.projectId) { participantOptions.value = []; return }
  try {
    const cards: CardRead[] = await getCardsForProject(props.projectId)
    const roleNames = cards.filter(c => c.card_type?.name === '角色卡').map(c => c.title?.trim()).filter(Boolean) as string[]
    participantOptions.value = Array.from(new Set(roleNames)).slice(0, 500)
  } catch {
    participantOptions.value = []
  }
}

onMounted(() => { loadParticipantOptions(); if (props.prefetched) assembled.value = props.prefetched })

async function assemble() {
  try {
    assembling.value = true
    const res = await assembleContext({
      project_id: props.projectId,
      volume_number: localVolumeNumber.value ?? undefined,
      chapter_number: localChapterNumber.value ?? undefined,
      participants: localParticipants.value,
      current_draft_tail: props.draftTail || ''
    })
    assembled.value = res
    // 将最新本地值回写父层，确保保存时同步
    emitParticipants(); emitVolume(); emitChapter();
    ElMessage.success('上下文已装配')
  } catch (e:any) {
    ElMessage.error('装配失败')
  } finally {
    assembling.value = false
  }
}
</script>

<style scoped>
.ctx-panel { display: flex; flex-direction: column; gap: 8px; height: 100%; }
.controls { padding: 8px; border-bottom: 1px solid var(--el-border-color-light); }
.actions { display: flex; gap: 8px; }
.assembled { padding: 8px; overflow: auto; color: var(--el-text-color-primary); font-size: 14px; line-height: 1.8; }
.pre { white-space: pre-wrap; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace; font-size: 13px; color: var(--el-text-color-primary); }
.budget { display: flex; gap: 12px; color: var(--el-text-color-regular); margin-top: 6px; font-size: 12px; }
.facts-structured { margin-bottom: 8px; }
.facts-title { font-weight: 600; margin: 6px 0; color: var(--el-text-color-primary); }
.list { margin: 0; padding-left: 16px; }
.list li { margin: 4px 0; }
.muted { color: var(--el-text-color-regular); }
.relation-item { margin-bottom: 10px; }
.relation-head { font-weight: 600; margin: 2px 0; color: var(--el-text-color-primary); }
.addressing span { display: inline-block; }
.dialog-text { white-space: pre-wrap; line-height: 1.8; font-size: 13.5px; color: var(--el-text-color-primary); }
.badges { margin-left: 8px; }
.raw-toggle { margin: 6px 0; }
</style> 