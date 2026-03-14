<template>
  <div class="markdown-renderer" v-html="renderedHtml"></div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import MarkdownIt from 'markdown-it'

const props = defineProps<{
  markdown: string
}>()

// 初始化 markdown-it 实例
const md = new MarkdownIt({
  html: false, // 禁用 HTML 标签（安全）
  linkify: true, // 自动转换 URL 为链接
  typographer: true, // 启用智能引号和其他排版优化
  breaks: false, // 不将换行符转换为 <br>
})

// 质量门禁结论的映射
const verdictMap: Record<string, string> = {
  'pass': '基本通过',
  'revise': '建议修改',
  'block': '高风险拦截'
}

const renderedHtml = computed(() => {
  if (!props.markdown) return ''
  let html = md.render(props.markdown)
  
  // 处理质量门禁的结论行，将英文值替换为中文并加粗
  // 匹配模式：- 结论：pass / revise / block
  html = html.replace(
    /(<li>结论[：:]\s*)(pass|revise|block)(\s*<\/li>)/gi,
    (match, prefix, verdict, suffix) => {
      const chineseVerdict = verdictMap[verdict.toLowerCase()] || verdict
      return `${prefix}<strong>${chineseVerdict}</strong>${suffix}`
    }
  )
  
  return html
})
</script>

<style scoped>
.markdown-renderer {
  color: var(--el-text-color-primary);
  font-size: 14px;
  line-height: 1.8;
  word-break: break-word;
}

/* 标题 */
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

.markdown-renderer :deep(h1) { font-size: 1.8em; }
.markdown-renderer :deep(h2) { font-size: 1.5em; }
.markdown-renderer :deep(h3) { font-size: 1.3em; }
.markdown-renderer :deep(h4) { font-size: 1.1em; }

/* 段落 */
.markdown-renderer :deep(p) {
  margin: 0.5em 0;
  color: var(--el-text-color-primary);
}

/* 列表 - 完全靠左，无缩进 */
.markdown-renderer :deep(ul),
.markdown-renderer :deep(ol) {
  margin: 0.5em 0;
  padding: 0;
  list-style-position: inside;
}

.markdown-renderer :deep(li) {
  margin: 0.2em 0;
  padding: 0;
  color: var(--el-text-color-primary);
}

/* 嵌套列表 */
.markdown-renderer :deep(ul ul),
.markdown-renderer :deep(ol ol),
.markdown-renderer :deep(ul ol),
.markdown-renderer :deep(ol ul) {
  margin-left: 1.5em;
}

/* 引用块 */
.markdown-renderer :deep(blockquote) {
  margin: 0.8em 0;
  padding: 0.5em 1em;
  border-left: 4px solid var(--el-color-primary);
  background: var(--el-fill-color-light);
  color: var(--el-text-color-secondary);
}

/* 代码 */
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

/* 粗体和斜体 */
.markdown-renderer :deep(strong) {
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.markdown-renderer :deep(em) {
  font-style: italic;
}

/* 链接 */
.markdown-renderer :deep(a) {
  color: var(--el-color-primary);
  text-decoration: none;
}

.markdown-renderer :deep(a:hover) {
  text-decoration: underline;
}

/* 分隔线 */
.markdown-renderer :deep(hr) {
  margin: 1.5em 0;
  border: none;
  border-top: 1px solid var(--el-border-color-light);
}

/* 表格 */
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
