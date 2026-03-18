<template>
  <div class="review-result-card-editor">
    <div class="review-header">
      <div class="review-header-main">
        <div class="review-title-block">
          <h2 class="review-title">{{ card.title }}</h2>
          <div class="review-meta">
            <el-tag :type="verdictTagType" effect="dark" size="small">{{ verdictLabel }}</el-tag>
            <el-tag v-if="reviewProfile" type="info" effect="plain" size="small">{{ reviewProfile }}</el-tag>
            <el-tag v-if="targetField" type="info" effect="plain" size="small">{{ targetField }}</el-tag>
            <span class="review-time">{{ reviewedAtText }}</span>
          </div>
        </div>
        <div class="review-actions">
          <el-button size="small" plain type="primary" @click="jumpToTarget">跳转被审核卡片</el-button>
        </div>
      </div>
      <div class="review-target">
        审核对象：{{ targetTitle || '未命名目标' }}
      </div>
    </div>

    <div class="review-body">
      <SimpleMarkdown :markdown="reviewMarkdown" class="review-markdown" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ElTag } from 'element-plus'
import type { CardRead } from '@renderer/api/cards'
import SimpleMarkdown from '../common/SimpleMarkdown.vue'

const props = defineProps<{
  card: CardRead
}>()

const content = computed(() => (props.card.content || {}) as Record<string, any>)
const targetTitle = computed(() => String(content.value.review_target_title || ''))
const reviewProfile = computed(() => String(content.value.review_profile || ''))
const targetField = computed(() => String(content.value.review_target_field || ''))
const reviewMarkdown = computed(() => String(content.value.review_markdown || '（暂无内容）'))
const reviewedAtText = computed(() => {
  const value = String(content.value.reviewed_at || '')
  if (!value) return ''
  try {
    return new Intl.DateTimeFormat('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(value))
  } catch {
    return value
  }
})

const verdictLabel = computed(() => {
  switch (content.value.quality_gate) {
    case 'pass':
      return '基本通过'
    case 'block':
      return '高风险拦截'
    default:
      return '建议修改'
  }
})

const verdictTagType = computed<'success' | 'warning' | 'danger'>(() => {
  switch (content.value.quality_gate) {
    case 'pass':
      return 'success'
    case 'block':
      return 'danger'
    default:
      return 'warning'
  }
})

function jumpToTarget() {
  const targetCardId = Number(content.value.review_target_card_id || 0)
  if (!targetCardId) return
  window.dispatchEvent(new CustomEvent('nf:jump-to-card', { detail: { cardId: targetCardId } }))
}
</script>

<style scoped>
.review-result-card-editor {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--el-bg-color);
}

.review-header {
  padding: 16px 20px;
  border-bottom: 1px solid var(--el-border-color-light);
  background: var(--el-fill-color-extra-light);
}

.review-header-main {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.review-title-block {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.review-title {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  color: var(--el-text-color-primary);
}

.review-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.review-time {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.review-target {
  margin-top: 10px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.review-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 18px 20px 24px;
}

:deep(.review-markdown) {
  color: var(--el-text-color-primary);
  font-size: 14px;
  line-height: 1.9;
  word-break: break-word;
}
</style>
