<template>
  <XMarkdown
    :markdown="renderedMarkdown"
    :default-theme-mode="isDarkMode ? 'dark' : 'light'"
    :allow-html="false"
    :enable-breaks="false"
    class="markdown-renderer"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { XMarkdown } from 'vue-element-plus-x'
import { useAppStore } from '@renderer/stores/useAppStore'

const props = defineProps<{
  markdown: string
}>()

const appStore = useAppStore()
const isDarkMode = computed(() => appStore.isDarkMode)

const verdictMap: Record<string, string> = {
  pass: '基本通过',
  revise: '建议修改',
  block: '高风险拦截'
}

function normalizeReviewMarkdown(markdown: string): string {
  if (!markdown) return ''

  const normalizedLines = markdown
    .replace(/\r\n/g, '\n')
    .split('\n')
    .map((line) => {
      if (/^\s+(##\s+|-\s+|\d+\.\s+)/.test(line)) {
        return line.replace(/^\s+/, '')
      }
      return line
    })

  const normalizedMarkdown = normalizedLines.join('\n').trim()

  return normalizedMarkdown.replace(
    /^(-\s*结论[：:]\s*)(pass|revise|block)(\s*)$/gim,
    (_, prefix: string, verdict: string, suffix: string) => {
      const localizedVerdict = verdictMap[verdict.toLowerCase()] || verdict
      return `${prefix}**${localizedVerdict}**${suffix}`
    }
  )
}

const renderedMarkdown = computed(() => normalizeReviewMarkdown(props.markdown))
</script>

<style scoped>
.markdown-renderer {
  color: var(--el-text-color-primary);
  font-size: 14px;
  line-height: 1.8;
  word-break: break-word;
}

.markdown-renderer :deep(.markdown-body) {
  padding: 0;
  background: transparent;
  color: inherit;
  font-size: inherit;
  line-height: inherit;
}

.markdown-renderer :deep(h1),
.markdown-renderer :deep(h2),
.markdown-renderer :deep(h3),
.markdown-renderer :deep(h4),
.markdown-renderer :deep(h5),
.markdown-renderer :deep(h6) {
  margin: 1em 0 0.5em 0;
  color: var(--el-text-color-primary);
  font-weight: 600;
  line-height: 1.4;
}

.markdown-renderer :deep(h1) {
  font-size: 1.8em;
}
.markdown-renderer :deep(h2) {
  font-size: 1.5em;
}
.markdown-renderer :deep(h3) {
  font-size: 1.3em;
}
.markdown-renderer :deep(h4) {
  font-size: 1.1em;
}

.markdown-renderer :deep(p) {
  margin: 0.5em 0;
  color: var(--el-text-color-primary);
}

.markdown-renderer :deep(ul),
.markdown-renderer :deep(ol) {
  margin: 0.5em 0;
  padding: 0;
  padding-inline-start: 0;
  list-style-position: inside;
}

.markdown-renderer :deep(li) {
  margin: 0.2em 0;
  padding: 0;
  color: var(--el-text-color-primary);
}

.markdown-renderer :deep(ul ul),
.markdown-renderer :deep(ol ol),
.markdown-renderer :deep(ul ol),
.markdown-renderer :deep(ol ul) {
  margin-left: 1.5em;
  padding-inline-start: 0;
}

.markdown-renderer :deep(blockquote) {
  margin: 0.8em 0;
  padding: 0.5em 1em;
  border-left: 4px solid var(--el-color-primary);
  background: var(--el-fill-color-light);
  color: var(--el-text-color-secondary);
}

.markdown-renderer :deep(code) {
  background: var(--el-fill-color-light);
  color: var(--el-color-danger);
  padding: 2px 6px;
  border-radius: 3px;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 0.9em;
}

.markdown-renderer :deep(pre) {
  background: var(--el-fill-color-extra-light);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 12px;
  overflow-x: auto;
  margin: 0.8em 0;
}

.markdown-renderer :deep(pre code) {
  background: transparent;
  color: var(--el-text-color-primary);
  padding: 0;
  font-size: 0.85em;
  line-height: 1.5;
}

.markdown-renderer :deep(strong) {
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.markdown-renderer :deep(em) {
  font-style: italic;
}

.markdown-renderer :deep(a) {
  color: var(--el-color-primary);
  text-decoration: none;
}

.markdown-renderer :deep(a:hover) {
  text-decoration: underline;
}

.markdown-renderer :deep(hr) {
  margin: 1.5em 0;
  border: none;
  border-top: 1px solid var(--el-border-color-light);
}

.markdown-renderer :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 0.8em 0;
}

.markdown-renderer :deep(th),
.markdown-renderer :deep(td) {
  border: 1px solid var(--el-border-color-light);
  padding: 8px 12px;
  text-align: left;
}

.markdown-renderer :deep(th) {
  background: var(--el-fill-color-light);
  font-weight: 600;
}

.markdown-renderer :deep(tr:nth-child(even)) {
  background: var(--el-fill-color-lighter);
}
</style>
