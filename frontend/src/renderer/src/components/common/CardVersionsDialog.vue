<template>
  <el-dialog v-model="visible" title="历史版本" width="80%">
    <div class="toolbar">
      <el-button size="small" @click="reload">刷新</el-button>
      <el-popconfirm title="清空该卡片的所有本地版本？" @confirm="clearAll">
        <template #reference>
          <el-button size="small" type="danger" plain>清空全部</el-button>
        </template>
      </el-popconfirm>
      <span class="tip">历史版本仅保存在前端，最多保留最近20条。</span>
    </div>

    <el-table :data="versions" style="width:100%" height="50vh" size="small" v-loading="loading">
      <el-table-column label="时间" width="200">
        <template #default="{ row }">{{ format(row.createdAt) }}</template>
      </el-table-column>
      <el-table-column prop="title" label="标题" width="240" />
      <el-table-column label="摘要(内容)" width="320">
        <template #default="{ row }">
          <span class="summary">{{ summarize(row.content) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="摘要(上下文)" width="320">
        <template #default="{ row }">
          <span class="summary">{{ summarizeCtx(row.ai_context_template) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="260">
        <template #default="{ row }">
          <el-button size="small" @click="preview(row)">预览</el-button>
          <el-popconfirm title="恢复该版本并覆盖当前内容？" @confirm="restore(row)">
            <template #reference>
              <el-button size="small" type="primary">恢复</el-button>
            </template>
          </el-popconfirm>
          <el-popconfirm title="删除该版本？" @confirm="remove(row)">
            <template #reference>
              <el-button size="small" type="danger" plain>删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <template #footer>
      <el-button @click="visible=false">关闭</el-button>
    </template>

    <!-- 预览抽屉：改为并排差异高亮渲染 -->
    <el-drawer v-model="drawerVisible" title="版本预览" size="70%">
      <div class="preview-wrap2">
        <div class="pane">
          <h4>内容对比</h4>
          <div class="diff-table">
            <div class="diff-header">所选版本</div>
            <div class="diff-header">当前</div>
            <template v-for="(row, idx) in contentDiffRows" :key="'c-'+idx">
              <pre class="diff-cell" :class="row.left?.type ? 'diff-' + row.left.type : 'diff-empty'">{{ row.left?.text || '' }}</pre>
              <pre class="diff-cell" :class="row.right?.type ? 'diff-' + row.right.type : 'diff-empty'">{{ row.right?.text || '' }}</pre>
            </template>
          </div>
        </div>
        <div class="pane">
          <h4>上下文模板对比</h4>
          <div class="diff-table">
            <div class="diff-header">所选版本</div>
            <div class="diff-header">当前</div>
            <template v-for="(row, idx) in contextDiffRows" :key="'x-'+idx">
              <pre class="diff-cell" :class="row.left?.type ? 'diff-' + row.left.type : 'diff-empty'">{{ row.left?.text || '' }}</pre>
              <pre class="diff-cell" :class="row.right?.type ? 'diff-' + row.right.type : 'diff-empty'">{{ row.right?.text || '' }}</pre>
            </template>
          </div>
        </div>
      </div>
    </el-drawer>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { listVersions, clearVersions, deleteVersion, type CardVersionSnapshot } from '@renderer/services/versionService'
import { ElMessage } from 'element-plus'

const props = defineProps<{ projectId: number; cardId: number; modelValue: boolean; currentContent: any; currentContextTemplate: string }>()
const emit = defineEmits(['update:modelValue','restore'])

const visible = ref(props.modelValue)
watch(() => props.modelValue, v => visible.value = v)
watch(visible, v => emit('update:modelValue', v))

const versions = ref<CardVersionSnapshot[]>([])
const loading = ref(false)

function reload() {
  loading.value = true
  versions.value = listVersions(props.projectId, props.cardId)
  loading.value = false
}

watch(() => props.cardId, reload, { immediate: true })

function format(iso: string) { return new Date(iso).toLocaleString() }
function summarize(content: any) {
  const s = JSON.stringify(content ?? {})
  return s.length > 100 ? s.slice(0, 100) + '…' : s
}
function summarizeCtx(ctx?: string) {
  const s = String(ctx ?? '')
  return s.length > 100 ? s.slice(0, 100) + '…' : s
}

function clearAll() {
  clearVersions(props.projectId, props.cardId)
  reload()
  ElMessage.success('已清空该卡片的本地版本')
}

function remove(v: CardVersionSnapshot) {
  deleteVersion(props.projectId, props.cardId, v.id)
  reload()
  ElMessage.success('已删除该版本')
}

const drawerVisible = ref(false)
const selectedText = ref('')
const selectedCtx = ref('')
const currentText = computed(() => JSON.stringify(props.currentContent ?? {}, null, 2))
const currentCtx = computed(() => props.currentContextTemplate ?? '')

function preview(v: CardVersionSnapshot) {
  selectedText.value = JSON.stringify(v.content ?? {}, null, 2)
  selectedCtx.value = v.ai_context_template ?? ''
  drawerVisible.value = true
}

function restore(v: CardVersionSnapshot) {
  emit('restore', v)
}

// 轻量行级差异算法（LCS 对齐）
// 输入两段文本，按行拆分后计算最短编辑路径对齐，输出左右并排渲染所需的数据结构
interface DiffPart { text: string; type: 'equal' | 'add' | 'del' }
interface DiffRow { left?: DiffPart; right?: DiffPart }

function computeDiffRows(left: string, right: string): DiffRow[] {
  const a = (left || '').split('\n')
  const b = (right || '').split('\n')
  const m = a.length, n = b.length
  // dp[i][j] 表示 a[0..i-1] 与 b[0..j-1] 的 LCS 长度
  const dp: number[][] = Array.from({ length: m + 1 }, () => Array(n + 1).fill(0))
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      dp[i][j] = a[i - 1] === b[j - 1] ? dp[i - 1][j - 1] + 1 : Math.max(dp[i - 1][j], dp[i][j - 1])
    }
  }
  // 回溯获取对齐路径
  const rows: DiffRow[] = []
  let i = m, j = n
  while (i > 0 && j > 0) {
    if (a[i - 1] === b[j - 1]) {
      rows.push({ left: { text: a[i - 1], type: 'equal' }, right: { text: b[j - 1], type: 'equal' } })
      i--; j--
    } else if (dp[i - 1][j] >= dp[i][j - 1]) {
      rows.push({ left: { text: a[i - 1], type: 'del' } })
      i--
    } else {
      rows.push({ right: { text: b[j - 1], type: 'add' } })
      j--
    }
  }
  while (i > 0) { rows.push({ left: { text: a[i - 1], type: 'del' } }); i-- }
  while (j > 0) { rows.push({ right: { text: b[j - 1], type: 'add' } }); j-- }
  rows.reverse()
  return rows
}

// 内容与上下文的并排差异结果
const contentDiffRows = computed<DiffRow[]>(() => computeDiffRows(selectedText.value, currentText.value))
const contextDiffRows = computed<DiffRow[]>(() => computeDiffRows(selectedCtx.value, currentCtx.value))
</script>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.tip { color: var(--el-text-color-secondary); font-size: 12px; margin-left: auto; }
.preview-wrap2 { display: grid; grid-template-columns: 1fr 1fr; grid-auto-rows: minmax(140px, auto); gap: 12px; }
.pane { overflow: auto; border: 1px solid var(--el-border-color-light); border-radius: 6px; padding: 8px; }
.summary { color: var(--el-text-color-secondary); }

/* 差异渲染：两列并排，行级高亮 */
.diff-table { display: grid; grid-template-columns: 1fr 1fr; border: 1px solid var(--el-border-color-light); border-radius: 4px; overflow: hidden; }
.diff-header { background: var(--el-fill-color-light); font-weight: 600; padding: 6px 8px; border-bottom: 1px solid var(--el-border-color-light); }
.diff-cell { margin: 0; white-space: pre-wrap; word-break: break-word; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; padding: 2px 6px; border-left: 3px solid transparent; border-bottom: 1px solid var(--el-border-color-extra-light); }
.diff-equal { background: transparent; }
.diff-add { background: rgba(46, 204, 113, 0.12); border-left-color: #2ecc71; }
.diff-del { background: rgba(231, 76, 60, 0.13); border-left-color: #e74c3c; }
.diff-empty { background: var(--el-fill-color-blank); }
</style> 