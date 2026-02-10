<template>
  <div class="markdown-text-editor">
    <div class="editor-toolbar">
      <div class="toolbar-left">
        <el-segmented v-model="mode" :options="modeOptions" size="small" />
      </div>
      <div class="toolbar-right">
        <span class="char-count">字数：{{ charCount }}</span>
      </div>
    </div>

    <div class="editor-body" v-if="mode === 'edit'">
      <el-input
        v-model="textContent"
        type="textarea"
        :rows="24"
        resize="none"
        placeholder="输入 Markdown 文本..."
        class="markdown-textarea"
      />
    </div>

    <div class="preview-body" v-else>
      <XMarkdown
        :markdown="textContent || '（暂无内容）'"
        default-theme-mode="light"
        class="markdown-preview"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { XMarkdown } from 'vue-element-plus-x'
import type { CardRead, CardUpdate } from '@renderer/api/cards'
import { useCardStore } from '@renderer/stores/useCardStore'

const props = defineProps<{
  card: CardRead
}>()

const emit = defineEmits<{
  (e: 'update:dirty', value: boolean): void
}>()

const cardStore = useCardStore()

const mode = ref<'edit' | 'preview'>('preview')
const modeOptions = [
  { label: '编辑', value: 'edit' },
  { label: '预览', value: 'preview' },
]

const textContent = ref('')
const originalContent = ref('')
const charCount = computed(() => {
  const text = textContent.value || ''
  const normalized = text.replace(/\s+/g, '')
  return normalized.length
})

function extractText(content: any): string {
  if (!content) return ''
  if (typeof content === 'string') return content
  if (typeof content === 'object' && typeof content.content === 'string') return content.content
  return ''
}

watch(
  () => props.card,
  (nextCard) => {
    const text = extractText(nextCard?.content)
    textContent.value = text
    originalContent.value = text
    emit('update:dirty', false)
  },
  { immediate: true, deep: true }
)

watch(textContent, (next) => {
  emit('update:dirty', next !== originalContent.value)
})

async function handleSave(newTitle?: string) {
  const effectiveTitle = typeof newTitle === 'string' && newTitle.trim()
    ? newTitle.trim()
    : props.card.title

  const nextContent = {
    ...(typeof props.card.content === 'object' && props.card.content ? props.card.content : {}),
    content: textContent.value,
  }

  const updatePayload: CardUpdate = {
    title: effectiveTitle,
    content: nextContent as any,
    needs_confirmation: false,
  }

  await cardStore.modifyCard(props.card.id, updatePayload)
  originalContent.value = textContent.value
  emit('update:dirty', false)
  return updatePayload.content
}

async function restoreContent(versionContent: any) {
  const text = extractText(versionContent)
  textContent.value = text
  originalContent.value = text
  emit('update:dirty', false)
}

defineExpose({
  handleSave,
  restoreContent,
})
</script>

<style scoped>
.markdown-text-editor {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.editor-toolbar {
  padding: 8px 12px;
  border-bottom: 1px solid var(--el-border-color-light);
  background: var(--el-fill-color-lighter);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
}

.char-count {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.editor-body,
.preview-body {
  flex: 1;
  min-height: 0;
  padding: 12px;
}

.markdown-textarea {
  height: 100%;
}

.markdown-textarea :deep(.el-textarea__inner) {
  height: 100% !important;
  min-height: 100% !important;
  font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
  line-height: 1.6;
}

.preview-body {
  overflow: auto;
}

.markdown-preview {
  min-height: 100%;
}
</style>
