<template>
  <div class="outline-panel">
    <div class="panel-pad">
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
            <li v-for="(b, i) in outline.branch_line" :key="i">{{ b.name || `支线${i+1}` }}：{{ b.overview || '暂无概述' }}</li>
          </ul>
        </div>
        <div v-if="Array.isArray(outline.stage_lines) && outline.stage_lines.length" class="section">
          <div class="sec-title">📖 阶段性故事线</div>
          <div class="stage" v-for="(st, i) in outline.stage_lines" :key="i">
            <div class="stage-head">
              <span class="name">{{ st.stage_name || `阶段${i+1}` }}</span>
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
      <template v-else>
        <div class="placeholder">暂无分卷大纲卡片</div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ outline?: any | null }>()

const hasOutline = computed(() => !!props.outline && typeof props.outline === 'object')
const outline = computed(() => props.outline || {})

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