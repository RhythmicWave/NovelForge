<template>
  <div class="review-history-panel">
    <template v-if="!selectedReview">
      <div class="panel-toolbar">
        <el-select v-model="reviewType" size="small" class="type-select">
          <el-option label="全部" value="all" />
          <el-option label="章节审核" value="chapter" />
          <el-option label="阶段审核" value="stage" />
        </el-select>
        <el-input
          v-model="targetTitleKeyword"
          size="small"
          clearable
          class="target-title-search"
          placeholder="搜索目标标题"
          @keyup.enter="loadReviews"
          @clear="loadReviews"
        />
        <el-button size="small" type="primary" plain @click="loadReviews">查询</el-button>
      </div>

      <div v-loading="loading" class="panel-body">
        <el-empty v-if="!loading && reviews.length === 0" description="暂无审核历史" :image-size="80" />

        <div v-else class="review-list">
          <div
            v-for="row in reviews"
            :key="row.id"
            class="review-list-item"
          >
            <div class="review-list-main">
              <el-tooltip
                :content="row.target_title || '未命名目标'"
                placement="top-start"
                :show-after="200"
              >
                <div class="review-title">
                  {{ row.target_title || '未命名目标' }}
                </div>
              </el-tooltip>

              <div class="review-list-meta">
                <el-tag size="small" effect="dark" :type="getVerdictTagType(row.quality_gate)">
                  {{ formatVerdict(row.quality_gate) }}
                </el-tag>
                <el-tag size="small" effect="plain" :type="row.review_type === 'stage' ? 'warning' : 'primary'">
                  {{ row.review_type === 'stage' ? '阶段审核' : '章节审核' }}
                </el-tag>
                <span class="review-time">{{ formatTime(row.created_at) }}</span>
                <div class="review-actions">
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
      </div>

      <div class="panel-body detail-body">
        <div class="review-detail-header">
          <h3 class="review-detail-title">
            {{ selectedReview.target_title || '未命名目标' }}
          </h3>
        </div>

        <div class="review-overview">
          <div class="review-overview-main">
            <el-tag
              :type="getVerdictTagType(selectedReview.quality_gate)"
              effect="dark"
            >
              {{ formatVerdict(selectedReview.quality_gate) }}
            </el-tag>
            <el-tag size="small" effect="plain" :type="selectedReview.review_type === 'stage' ? 'warning' : 'primary'">
              {{ selectedReview.review_type === 'stage' ? '阶段审核' : '章节审核' }}
            </el-tag>
            <span class="review-score">
              记录于 {{ formatTime(selectedReview.created_at) }}
            </span>
          </div>
          <p class="review-summary">本次审核已按标准审校单格式存档，可直接用于回看和历史查询。</p>
        </div>

        <div class="review-text-block">
          <SimpleMarkdown
            :markdown="selectedReview.result_text || '（暂无内容）'"
            class="review-markdown"
          />
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import SimpleMarkdown from '../common/SimpleMarkdown.vue'
import { deleteReview, listProjectReviews, type ReviewRecord } from '@renderer/api/chapterReviews'
import { useAppStore } from '@renderer/stores/useAppStore'

const props = defineProps<{
  projectId?: number | null
  defaultReviewType?: 'all' | 'chapter' | 'stage'
}>()

const loading = ref(false)
const reviewType = ref<'all' | 'chapter' | 'stage'>(props.defaultReviewType ?? 'all')
const targetTitleKeyword = ref('')
const reviews = ref<ReviewRecord[]>([])
const selectedReview = ref<ReviewRecord | null>(null)
const appStore = useAppStore()
const isDarkMode = computed(() => appStore.isDarkMode)

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

function openDetail(item: ReviewRecord) {
  selectedReview.value = item
}

function backToList() {
  selectedReview.value = null
}

async function loadReviews() {
  if (!props.projectId) {
    reviews.value = []
    return
  }

  loading.value = true
  try {
    reviews.value = await listProjectReviews(props.projectId, reviewType.value, targetTitleKeyword.value)
  } catch (error) {
    console.error('Failed to load review history:', error)
    ElMessage.error('加载审核历史失败')
  } finally {
    loading.value = false
  }
}

async function handleDelete(item: ReviewRecord) {
  try {
    await ElMessageBox.confirm(
      `确认删除审核记录「${item.target_title || '未命名目标'}」吗？此操作不可恢复。`,
      '删除确认',
      { type: 'warning' }
    )
  } catch {
    return
  }

  try {
    await deleteReview(item.id)
    if (selectedReview.value?.id === item.id) {
      selectedReview.value = null
    }
    reviews.value = reviews.value.filter(review => review.id !== item.id)
    ElMessage.success('审核记录已删除')
  } catch (error) {
    console.error('Failed to delete review record:', error)
  }
}

function handleReviewHistoryRefresh() {
  loadReviews()
}

watch(
  () => props.defaultReviewType,
  (value) => {
    reviewType.value = value ?? 'all'
    selectedReview.value = null
    loadReviews()
  }
)

watch(
  () => props.projectId,
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

.panel-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px;
  border-bottom: 1px solid var(--el-border-color-light);
}

.type-select {
  width: 140px;
}

.target-title-search {
  flex: 1;
  min-width: 0;
}

.panel-body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  padding: 10px;
}

.detail-toolbar {
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
  max-height: 60vh;
  overflow: auto;
  padding: 12px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-bg-color);
}

:deep(.review-markdown) {
  font-size: 13px;
  line-height: 1.7;
  color: var(--el-text-color-primary);
  word-break: break-word;
}

:deep(.review-markdown h1),
:deep(.review-markdown h2),
:deep(.review-markdown h3),
:deep(.review-markdown h4),
:deep(.review-markdown h5),
:deep(.review-markdown h6) {
  margin-top: 0;
  color: var(--el-text-color-primary);
}

:deep(.review-markdown p),
:deep(.review-markdown li),
:deep(.review-markdown blockquote) {
  color: var(--el-text-color-primary);
}

:deep(.review-markdown pre) {
  background: var(--el-fill-color-extra-light);
  border: 1px solid var(--el-border-color-lighter);
}

:deep(.review-markdown code) {
  background: var(--el-fill-color-light);
  color: var(--el-text-color-primary);
}
</style>
