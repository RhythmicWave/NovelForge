<template>
  <div class="outline-panel">
    <div class="panel-pad">
      <template v-if="hasAny">
        <!-- 章节大纲 -->
        <template v-if="chapterOutline">
          <h4 class="title">章节大纲</h4>
          <div class="section">
            <div class="stage-head">
              <span class="name">第{{ chapterOutline.chapter_number || '-' }}章｜{{ chapterOutline.title || '未命名' }}</span>
              <span class="badge">卷{{ volumeNumber ?? '-' }}</span>
            </div>
            <p class="text">{{ chapterOutline.overview || '暂无概述' }}</p>
          </div>
        </template>

        <!-- 当前阶段（推导或外部传入） -->
        <template v-if="stageNow">
          <h4 class="title">当前阶段</h4>
          <div class="section">
            <div class="stage-head">
              <span class="name">{{ stageNow.stage_name || `阶段${stageNow.stage_number || '-'}` }}</span>
              <span v-if="Array.isArray(stageNow.reference_chapter) && stageNow.reference_chapter.length === 2" class="badge">第{{ stageNow.reference_chapter[0] }}-{{ stageNow.reference_chapter[1] }}章</span>
            </div>
            <p class="text">{{ stageNow.overview || '暂无概述' }}</p>
            <p v-if="stageNow.analysis" class="analysis"><b>创作分析：</b>{{ stageNow.analysis }}</p>
          </div>
        </template>

        <!-- 分卷大纲速查（原有） -->
        <template v-if="hasOutline">
          <h4 class="title">分卷大纲速查</h4>
          <div v-if="outline.thinking" class="section">
            <div class="sec-title">💭 创作思考</div>
            <p class="text">{{ outline.thinking }}</p>
          </div>
          <div v-if="outline.main_target" class="section">
            <div class="sec-title">🎯 主线目标</div>
            <p class="text"><b>名称：</b>{{ outline.main_target.name || '未设置' }}</p>
            <p class="text"><b>概述：</b>{{ outline.main_target.overview || '暂无概述' }}</p>
          </div>
          <div v-if="Array.isArray(outline.branch_line) && outline.branch_line.length" class="section">
            <div class="sec-title">🌿 支线剧情</div>
            <ul class="list">
              <li v-for="(b, i) in outline.branch_line" :key="i">{{ b.name || `支线${Number(i)+1}` }}：{{ b.overview || '暂无概述' }}</li>
            </ul>
          </div>
          <div v-if="Array.isArray(outline.stage_lines) && outline.stage_lines.length" class="section">
            <div class="sec-title">📖 阶段性故事线</div>
            <div class="stage" v-for="(st, i) in outline.stage_lines" :key="i">
              <div class="stage-head">
                <span class="name">{{ st.stage_name || `阶段${Number(i)+1}` }}</span>
                <span v-if="Array.isArray(st.reference_chapter) && st.reference_chapter.length === 2" class="badge">第{{ st.reference_chapter[0] }}-{{ st.reference_chapter[1] }}章</span>
              </div>
              <p class="text">{{ st.overview || '暂无概述' }}</p>
              <p v-if="st.analysis" class="analysis"><b>创作分析：</b>{{ st.analysis }}</p>
            </div>
          </div>
          <div v-if="Array.isArray(outline.character_snapshot) && outline.character_snapshot.length" class="section">
            <div class="sec-title">🧭 卷末快照</div>
            <ul class="list">
              <li v-for="(s, i) in outline.character_snapshot" :key="i">{{ s }}</li>
            </ul>
          </div>
        </template>
      </template>
      <template v-else>
        <div class="placeholder">暂无可用大纲</div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, watch, ref } from 'vue'
import { useCardStore } from '@renderer/stores/useCardStore'
import { storeToRefs } from 'pinia'
import type { CardRead } from '@renderer/api/cards'

const props = defineProps<{ 
  outline?: any | null
  currentStage?: any | null
  volumeNumber?: number | null
  chapterNumber?: number | null
  activeCard?: CardRead | null
}>()

const { cards } = storeToRefs(useCardStore())

// 内部状态：当activeCard存在且outline未提供时，自动查找
const internalOutline = ref<any | null>(null)
const internalCurrentStage = ref<any | null>(null)

// 查找分卷大纲
function findVolumeOutline(card: CardRead | null): void {
  internalOutline.value = null
  internalCurrentStage.value = null
  
  if (!card || !card.parent_id) return
  
  const parent = cards.value?.find(c => c.id === card.parent_id)
  if (!parent) return
  
  if (parent.card_type?.name === '分卷大纲') {
    internalOutline.value = parent.content
    
    // 根据章节号匹配所处阶段
    try {
      const stageLines: any[] = Array.isArray((parent.content as any)?.stage_lines) 
        ? (parent.content as any).stage_lines 
        : []
      const chNo = props.chapterNumber
      
      if (typeof chNo === 'number') {
        internalCurrentStage.value = stageLines.find(st => 
          Array.isArray(st.reference_chapter) && 
          st.reference_chapter.length === 2 && 
          chNo >= st.reference_chapter[0] && 
          chNo <= st.reference_chapter[1]
        ) || null
      }
    } catch (e) {
      console.error('Failed to find stage line:', e)
    }
  } else {
    // 递归查找父级
    findVolumeOutline(parent as any)
  }
}

// 当 activeCard 或卡片仓库内容发生变化时自动查找大纲
watch(
  [() => props.activeCard, cards],
  ([card]) => {
    if (card && !props.outline) {
      findVolumeOutline(card as CardRead)
    } else if (!card) {
      internalOutline.value = null
      internalCurrentStage.value = null
    }
  },
  { immediate: true }
)

const hasOutline = computed(() => {
  const o = props.outline || internalOutline.value
  return !!o && typeof o === 'object'
})

const outline = computed(() => props.outline || internalOutline.value || {})

// 若未传入 currentStage，则从分卷大纲中根据章节号推导
const stageNow = computed(() => {
  if (props.currentStage) return props.currentStage
  if (internalCurrentStage.value) return internalCurrentStage.value
  try {
    // 1) 优先从分卷大纲的 stage_lines 推导
    const sl = (outline.value?.stage_lines || []) as any[]
    const ch = Number(props.chapterNumber)
    if (Array.isArray(sl) && sl.length && Number.isFinite(ch)) {
      const hit = sl.find(st => Array.isArray(st.reference_chapter) && st.reference_chapter.length === 2 && ch >= Number(st.reference_chapter[0]) && ch <= Number(st.reference_chapter[1]))
      if (hit) return hit
    }
    // 2) 回退：从卡片仓库中查找“阶段大纲”卡
    const vol = Number(props.volumeNumber)
    if (!Number.isFinite(vol)) return null
    const all = (cards.value || [])
    if (!all.length) return null
    // 构建 id->card 映射，便于向上追溯祖先
    const idMap = new Map<number, any>(all.map(c => [c.id, c]))
    // 定位当前卷的分卷大纲卡
    const volumeCard = all.find(c => c?.card_type?.name === '分卷大纲' && Number(((c.content as any)?.volume_outline?.volume_number)) === vol)
    // 候选阶段卡：card_type 名称为“阶段大纲”，且同属该卷（祖先包含 volumeCard 或 content.volume_number==vol）
    const stageCards = all.filter(c => {
      if (c?.card_type?.name !== '阶段大纲') return false
      const contentVol = Number(((c.content as any)?.volume_number))
      if (Number.isFinite(contentVol) && contentVol === vol) return true
      if (volumeCard && c.parent_id) {
        let p = c as any
        for (let i=0; i<6 && p?.parent_id; i++) {
          p = idMap.get(p.parent_id)
          if (p?.id === volumeCard.id) return true
        }
      }
      return false
    })
    if (!stageCards.length) return null
    // 优先按章节号匹配 reference_chapter
    if (Number.isFinite(ch)) {
      const byRange = stageCards.find(c => Array.isArray((c.content as any)?.reference_chapter) && ch >= Number((c.content as any).reference_chapter[0]) && ch <= Number((c.content as any).reference_chapter[1]))
      if (byRange) return (byRange.content as any)
    }
    // 次选：若某卡 content.stage_number 恰好与 props.currentStage?.stage_number（若外部提供）一致
    const sn = Number((props.currentStage as any)?.stage_number)
    if (Number.isFinite(sn)) {
      const byIndex = stageCards.find(c => Number((c.content as any)?.stage_number) === sn)
      if (byIndex) return (byIndex.content as any)
    }
    // 最后回退：取第一个阶段卡
    const first = stageCards[0]
    return first ? (first.content as any) : null
  } catch { return null }
})

// 章节大纲：扫描所有卡片，匹配当前卷/章
const chapterOutline = computed(() => {
  try {
    const vol = Number(props.volumeNumber)
    const ch = Number(props.chapterNumber)
    if (!Number.isFinite(vol) || !Number.isFinite(ch)) return null
    const list = (cards.value || []).filter(c => c?.card_type?.name === '章节大纲')
    for (const c of list) {
      const co = (c.content as any)?.chapter_outline || (c.content as any)
      const v = Number(co?.volume_number)
      const n = Number(co?.chapter_number)
      if (Number.isFinite(v) && Number.isFinite(n) && v === vol && n === ch) {
        return {
          title: co?.title || c.title,
          overview: co?.overview || '',
          volume_number: v,
          chapter_number: n,
        }
      }
    }
  } catch {}
  return null
})

const hasAny = computed(() => !!chapterOutline.value || !!stageNow.value || !!hasOutline.value)
</script>

<style scoped>
.outline-panel { height: 100%; overflow: auto; }
.panel-pad { padding: 10px; color: var(--el-text-color-regular); }
.title { margin: 0 0 8px 0; font-size: 16px; font-weight: 600; color: var(--el-text-color-primary); }
.section { margin: 10px 0; padding: 12px; background: var(--el-fill-color-lighter); border-radius: 6px; }
.sec-title { font-weight: 600; margin-bottom: 6px; font-size: 14px; color: var(--el-text-color-primary); }
.text { margin: 4px 0; white-space: pre-wrap; font-size: 14px; line-height: 1.8; letter-spacing: 0.2px; color: var(--el-text-color-primary); }
.list { margin: 0; padding-left: 16px; font-size: 14px; line-height: 1.8; color: var(--el-text-color-primary); }
.stage { margin: 8px 0; padding: 8px; background: var(--el-bg-color); border-radius: 6px; border-left: 3px solid var(--el-color-primary); }
.stage-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px; }
.name { font-weight: 600; font-size: 14px; color: var(--el-text-color-primary); }
.placeholder { color: var(--el-text-color-secondary); }
.badge { font-size: 12px; color: var(--el-color-warning); border: 1px solid var(--el-color-warning); border-radius: 3px; padding: 0 6px; }
/* 高对比度调试样式 */
.debug-box { background: #1e1e1e; border-radius: 6px; padding: 8px; max-height: 260px; overflow: auto; }
.debug-pre { color: #e6e6e6; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace; font-size: 12px; line-height: 1.6; margin: 0; white-space: pre; }
</style> 