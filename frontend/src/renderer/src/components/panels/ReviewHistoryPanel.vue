<template>
  <div class="review-history-panel">
    <template v-if="!selectedReview">
      <div v-loading="loading" class="panel-body">
        <el-empty
          v-if="!loading && reviews.length === 0"
          description="当前卡片暂无审核结果卡片"
          :image-size="80"
        />

        <div v-else class="review-list">
          <div
            v-for="row in reviews"
            :key="row.card_id"
            class="review-list-item"
          >
            <div class="review-list-main">
              <el-tooltip
                :content="row.title"
                placement="top-start"
                :show-after="200"
              >
                <div class="review-title">
                  {{ row.title }}
                </div>
              </el-tooltip>

              <div class="review-list-meta">
                <el-tag size="small" effect="dark" :type="getVerdictTagType(row.quality_gate)">
                  {{ formatVerdict(row.quality_gate) }}
                </el-tag>
                <el-tag size="small" effect="plain" :type="getReviewTypeTagType(row.review_type)">
                  {{ formatReviewType(row.review_type) }}
                </el-tag>
                <el-tag v-if="row.review_profile" size="small" effect="plain" type="info">
                  {{ row.review_profile }}
                </el-tag>
                <el-tag v-if="row.review_target_field" size="small" effect="plain" type="info">
                  {{ row.review_target_field }}
                </el-tag>
                <span class="review-time">{{ formatTime(row.reviewed_at) }}</span>
                <div class="review-actions">
                  <el-button size="small" plain type="success" class="review-action-button" @click="addToAssistant(row)">
                    引用助手
                  </el-button>
                  <el-button size="small" plain type="primary" class="review-action-button" @click="openDetail(row)">
                    详情
                  </el-button>
                  <el-button size="small" plain type="danger" class="review-action-button" @click="handleDelete(row)">
                    删除
                  </el-button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>

    <template v-else>
      <div class="panel-toolbar detail-toolbar">
        <el-button size="small" @click="backToList">返回</el-button>
        <el-button
          size="small"
          type="success"
          plain
          @click="addToAssistant(selectedReview)"
        >
          引用到灵感助手
        </el-button>
      </div>

      <div class="panel-body detail-body">
        <div class="review-detail-header">
          <h3 class="review-detail-title">
            {{ selectedReview.title }}
          </h3>
        </div>

        <div class="review-overview">
          <div class="review-overview-main">
            <el-tag :type="getVerdictTagType(selectedReview.quality_gate)" effect="dark">
              {{ formatVerdict(selectedReview.quality_gate) }}
            </el-tag>
            <el-tag size="small" effect="plain" :type="getReviewTypeTagType(selectedReview.review_type)">
              {{ formatReviewType(selectedReview.review_type) }}
            </el-tag>
            <el-tag v-if="selectedReview.review_profile" size="small" effect="plain" type="info">
              {{ selectedReview.review_profile }}
            </el-tag>
            <el-tag v-if="selectedReview.review_target_field" size="small" effect="plain" type="info">
              {{ selectedReview.review_target_field }}
            </el-tag>
            <span class="review-score">
              更新于 {{ formatTime(selectedReview.reviewed_at) }}
            </span>
          </div>
          <p class="review-summary">该卡片展示当前最新审核结果，并与被审核卡片保持绑定。</p>
        </div>

        <div class="review-text-block">
          <SimpleMarkdown
            :markdown="selectedReview.review_markdown || '（暂无内容）'"
            class="review-markdown"
          />
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import SimpleMarkdown from '../common/SimpleMarkdown.vue'
import {
  deleteReviewCard,
  listTargetReviewCards,
  type ReviewResultCard,
} from '@renderer/api/chapterReviews'

const props = defineProps<{
  targetCardId?: number | null
}>()

const loading = ref(false)
const reviews = ref<ReviewResultCard[]>([])
const selectedReview = ref<ReviewResultCard | null>(null)

function formatVerdict(verdict?: string | null): string {
  switch (verdict) {
    case 'pass':
      return '基本通过'
    case 'block':
      return '高风险拦截'
    default:
      return '建议修改'
  }
}

function getVerdictTagType(verdict?: string | null): 'success' | 'warning' | 'danger' {
  switch (verdict) {
    case 'pass':
      return 'success'
    case 'block':
      return 'danger'
    default:
      return 'warning'
  }
}

function formatReviewType(type?: string | null): string {
  switch (type) {
    case 'chapter':
      return '章节审核'
    case 'stage':
      return '阶段审核'
    case 'card':
      return '通用卡片审核'
    case 'custom':
      return '自定义审核'
    default:
      return '审核'
  }
}

function getReviewTypeTagType(type?: string | null): 'primary' | 'warning' | 'success' | 'info' {
  switch (type) {
    case 'stage':
      return 'warning'
    case 'card':
      return 'success'
    case 'custom':
      return 'info'
    default:
      return 'primary'
  }
}

function formatTime(value?: string | null): string {
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
}

function openDetail(item: ReviewResultCard) {
  selectedReview.value = item
}

function backToList() {
  selectedReview.value = null
}

function addToAssistant(item: ReviewResultCard) {
  window.dispatchEvent(new CustomEvent('nf:assistant-add-review-ref', {
    detail: {
      ref: {
        refType: 'review_result',
        projectId: item.project_id,
        reviewCardId: item.card_id,
        targetId: item.review_target_card_id,
        targetTitle: item.review_target_title || '未命名目标',
        reviewType: item.review_type,
        reviewProfile: item.review_profile || null,
        qualityGate: item.quality_gate,
        resultText: item.review_markdown,
        contentSnapshot: item.target_snapshot || null,
        source: 'manual',
      },
    },
  }))
  ElMessage.success('已将审核结果卡片引用到灵感助手')
}

async function loadReviews() {
  if (!props.targetCardId) {
    reviews.value = []
    return
  }

  loading.value = true
  try {
    reviews.value = await listTargetReviewCards(props.targetCardId)
  } catch (error) {
    console.error('Failed to load review result cards:', error)
    ElMessage.error('加载审核结果卡片失败')
  } finally {
    loading.value = false
  }
}

async function handleDelete(item: ReviewResultCard) {
  try {
    await ElMessageBox.confirm(
      `确认删除审核结果卡片「${item.title}」吗？此操作不可恢复。`,
      '删除确认',
      { type: 'warning' }
    )
  } catch {
    return
  }

  try {
    await deleteReviewCard(item.card_id)
    if (selectedReview.value?.card_id === item.card_id) {
      selectedReview.value = null
    }
    reviews.value = reviews.value.filter(review => review.card_id !== item.card_id)
    ElMessage.success('审核结果卡片已删除')
  } catch (error) {
    console.error('Failed to delete review result card:', error)
  }
}

function handleReviewHistoryRefresh() {
  loadReviews()
}

watch(
  () => props.targetCardId,
  () => {
    selectedReview.value = null
    loadReviews()
  },
  { immediate: true }
)

onMounted(() => {
  window.addEventListener('nf:review-history-refresh', handleReviewHistoryRefresh)
})

onBeforeUnmount(() => {
  window.removeEventListener('nf:review-history-refresh', handleReviewHistoryRefresh)
})
</script>

<style scoped>
.review-history-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--el-bg-color);
}

.panel-body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  padding: 10px;
}

.detail-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px;
  border-bottom: 1px solid var(--el-border-color-light);
  justify-content: flex-start;
}

.detail-body {
  overflow-y: auto;
}

.review-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: 100%;
  overflow-y: auto;
}

.review-list-item {
  padding: 10px 12px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 10px;
  background: var(--el-fill-color-extra-light);
}

.review-list-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.review-title {
  min-width: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.review-list-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  flex-wrap: wrap;
}

.review-time {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}

.review-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.review-action-button {
  padding: 5px 10px;
}

.review-detail-header {
  margin-bottom: 12px;
}

.review-detail-title {
  margin: 0;
  font-size: 16px;
  line-height: 1.5;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.review-overview {
  padding: 12px;
  border-radius: 8px;
  background: var(--el-fill-color-lighter);
}

.review-overview-main {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.review-score {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.review-summary {
  margin: 0;
  font-size: 13px;
  line-height: 1.7;
  color: var(--el-text-color-regular);
}

.review-text-block {
  margin-top: 12px;
  padding: 16px;
  border-radius: 10px;
  border: 1px solid var(--el-border-color-lighter);
  background: var(--el-bg-color);
}

:deep(.review-markdown) {
  color: var(--el-text-color-primary);
  font-size: 14px;
  line-height: 1.8;
  word-break: break-word;
}
</style>
