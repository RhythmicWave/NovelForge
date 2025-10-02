<template>
  <div class="ctx-panel">
    <div class="panel-header">
      <h3 class="panel-title">参与实体</h3>
      <el-button size="small" type="primary" :loading="assembling" @click="assemble">刷新上下文</el-button>
    </div>
    
    <el-form label-width="70px" class="controls">
      <el-form-item label="参与者">
        <el-select v-model="localParticipants" multiple filterable allow-create default-first-option placeholder="输入或选择参与者" @change="onParticipantsChange">
          <el-option-group v-for="g in participantGroups" :key="g.label" :label="g.label">
            <el-option v-for="p in g.values" :key="p" :label="p" :value="p" />
          </el-option-group>
        </el-select>
      </el-form-item>
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
            <div class="relation-head">{{ (r as any).a }} ↔ {{ (r as any).b }}（{{ (r as any).kind }}）
              <el-tag v-if="(r as any).stance" size="small" style="margin-left:6px;">{{ (r as any).stance }}</el-tag>
            </div>
            <div v-if="(r as any).description" class="muted" style="margin: 2px 0;">{{ (r as any).description }}</div>
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
        
      </div>
      <pre class="pre" v-if="!assembled.facts_structured && assembled.facts_subgraph">{{ assembled.facts_subgraph }}</pre>
      <div v-if="!assembled.facts_structured && !assembled.facts_subgraph">关键事实：暂无（相关实体之间信息尚未收集）。</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { assembleContext, type AssembleContextResponse } from '@renderer/api/ai'
import { ElMessage } from 'element-plus'
import { getCardsForProject, type CardRead } from '@renderer/api/cards'

const props = defineProps<{ projectId?: number; participants?: string[]; volumeNumber?: number | null; stageNumber?: number | null; chapterNumber?: number | null; draftTail?: string; prefetched?: AssembleContextResponse | null }>()
const emit = defineEmits<{ (e:'update:participants', v: string[]): void; (e:'update:volumeNumber', v: number | null): void; (e:'update:stageNumber', v: number | null): void; (e:'update:chapterNumber', v: number | null): void }>()

const assembling = ref(false)
const assembled = ref<AssembleContextResponse | null>(null)
// 回显入口已移除

type Group = { label: string; values: string[] }
const participantGroups = ref<Group[]>([])
const localParticipants = ref<string[]>(props.participants || [])
const localVolumeNumber = ref<number | null>(props.volumeNumber ?? null)
const localStageNumber = ref<number | null>(props.stageNumber ?? null)
const localChapterNumber = ref<number | null>(props.chapterNumber ?? null)

// 缓存：名称 -> 分组标签（通过项目卡片匹配）
const nameToGroup = ref<Record<string, string>>({})

watch(() => props.participants, (v) => { localParticipants.value = [...(v || [])] })
watch(() => props.volumeNumber, (v) => { localVolumeNumber.value = v ?? null })
watch(() => props.stageNumber, (v) => { localStageNumber.value = v ?? null })
watch(() => props.chapterNumber, (v) => { localChapterNumber.value = v ?? null })
watch(() => props.prefetched, (v) => { if (v) assembled.value = v })
watch(() => props.projectId, async () => { await buildNameGroupCache(); await buildAllGroups() })

function emitParticipants() { emit('update:participants', [...localParticipants.value]) }
function emitVolume() { emit('update:volumeNumber', localVolumeNumber.value ?? null) }
function emitStage() { emit('update:stageNumber', localStageNumber.value ?? null) }
function emitChapter() { emit('update:chapterNumber', localChapterNumber.value ?? null) }

function detectTypeGroupByCard(c: CardRead): string {
  // 1) 优先使用内容中的实体类型标记（后端新增）
  const et = (c.content as any)?.entity_type
  if (et === 'character') return '角色'
  if (et === 'scene') return '场景'
  if (et === 'organization') return '组织'
  if (et === 'item') return '物品'
  if (et === 'concept') return '概念'

  // 2) 使用卡片类型中文名归类
  const tname = (c.card_type?.name || '').trim()
  if (tname.includes('角色')) return '角色'
  if (tname.includes('场景')) return '场景'
  if (tname.includes('组织')) return '组织'
  if (tname.includes('物品')) return '物品'
  if (tname.includes('概念')) return '概念'

  // 3) 兼容旧模型名：优先实例/类型的 model_name
  const m = (c as any).model_name || (c.card_type as any)?.model_name || ''
  if (m === 'CharacterCard') return '角色'
  if (m === 'SceneCard') return '场景'
  if (m === 'OrganizationCard') return '组织'

  return '其他'
}

async function buildNameGroupCache() {
  nameToGroup.value = {}
  if (!props.projectId) return
  try {
    const cards: CardRead[] = await getCardsForProject(props.projectId)
    for (const c of cards) {
      const nm = (c.title || '').trim()
      if (!nm) continue
      nameToGroup.value[nm] = detectTypeGroupByCard(c)
    }
  } catch {}
}

async function buildAllGroups() {
  if (!props.projectId) { participantGroups.value = []; return }
  try {
    const cards: CardRead[] = await getCardsForProject(props.projectId)
    const order = ['角色','场景','组织','物品','概念','其他']
    const buckets = new Map<string, Set<string>>()
    order.forEach(t => buckets.set(t, new Set<string>()))
    for (const c of cards) {
      const t = detectTypeGroupByCard(c)
      const title = (c.title || '').trim()
      if (!title) continue
      buckets.get(t)!.add(title)
    }
    participantGroups.value = order
      .map(label => ({ label, values: Array.from(buckets.get(label) || []).sort((a,b)=>a.localeCompare(b)) }))
      .filter(g => g.values.length > 0)
  } catch {
    participantGroups.value = []
  }
}

function onParticipantsChange() {
  emitParticipants();
}

onMounted(async () => { await buildNameGroupCache(); await buildAllGroups(); if (props.prefetched) assembled.value = props.prefetched })

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
    emitParticipants(); emitVolume(); emitStage(); emitChapter();
    ElMessage.success('上下文已装配')
  } catch (e:any) {
    ElMessage.error('装配失败')
  } finally {
    assembling.value = false
  }
}
</script>

<style scoped>
.ctx-panel { display: flex; flex-direction: column; gap: 0; height: 100%; }
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 2px solid var(--el-border-color-light);
  background: var(--el-fill-color-lighter);
}
.panel-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.controls { padding: 12px 16px; border-bottom: 1px solid var(--el-border-color-light); }
.actions { display: flex; gap: 8px; }
.assembled { padding: 16px; overflow: auto; color: var(--el-text-color-primary); font-size: 14px; line-height: 1.8; }
.pre { white-space: pre-wrap; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace; font-size: 13px; color: var(--el-text-color-primary); }
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