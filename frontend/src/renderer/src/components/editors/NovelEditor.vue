<template>
  <div v-if="editor" class="editor-container">
    <div class="toolbar">
      <el-button-group>
        <el-tooltip content="加粗 (Ctrl+B)" placement="bottom">
          <el-button :type="editor.isActive('bold') ? 'primary' : ''" @click="editor.chain().focus().toggleBold().run()">B</el-button>
        </el-tooltip>
        <el-tooltip content="斜体 (Ctrl+I)" placement="bottom">
          <el-button :type="editor.isActive('italic') ? 'primary' : ''" @click="editor.chain().focus().toggleItalic().run()">I</el-button>
        </el-tooltip>
        <el-tooltip content="下划线 (Ctrl+U)" placement="bottom">
          <el-button :type="editor.isActive('underline') ? 'primary' : ''" @click="editor.chain().focus().toggleUnderline().run()">U</el-button>
        </el-tooltip>
        <el-tooltip content="高亮" placement="bottom">
           <el-button :type="editor.isActive('highlight') ? 'primary' : ''" @click="editor.chain().focus().toggleHighlight().run()">Hl</el-button>
        </el-tooltip>
      </el-button-group>

      <el-button-group class="mx-2">
        <el-tooltip content="自动缩进" placement="bottom">
          <el-button :type="autoIndent ? 'primary' : ''" @click="toggleAutoIndent">缩进</el-button>
        </el-tooltip>
      </el-button-group>

      <div class="flex-spacer"></div>

      <span class="word-count-display">{{ wordCount }} 字</span>

      <el-popover placement="bottom-end" title="AI续写设置" :width="400" trigger="click">
        <!-- 可在此添加参数卡选择器等设置 -->
      </el-popover>
      
      <el-button @click="executeAIContinuation" type="primary" :loading="aiLoading">
        AI续写
      </el-button>
      <el-button @click="handleSave" type="success" class="ml-2">
        保存
      </el-button>
    </div>
    <div class="editor-content-wrapper">
      <div class="chapter-title-display">
        <div class="chapter-title-wrapper">
          <h1 class="chapter-title-text">{{ localCard.title }}</h1>
        </div>
      </div>
      <EditorContent :editor="editor" class="editor-content" @keydown="handleKeydown" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { useEditor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Underline from '@tiptap/extension-underline'
import Highlight from '@tiptap/extension-highlight'
import TextAlign from '@tiptap/extension-text-align'
import { watch, onUnmounted, ref, reactive } from 'vue'
import { generateContinuationStreaming, type ContinuationRequest } from '@renderer/api/ai'
import type { CardRead, CardUpdate } from '@renderer/api/cards'
import { useCardStore } from '@renderer/stores/useCardStore'
import { useAIParamCardStore } from '@renderer/stores/useAIParamCardStore'
import { ElMessage } from 'element-plus'

const props = defineProps<{ card: CardRead }>()

const cardStore = useCardStore()
const aiParamCardStore = useAIParamCardStore()

// 当前选中的参数卡ID（来源于卡片的 selected_ai_param_card_id）
const selectedAiParamCardId = ref<string | undefined>(props.card.selected_ai_param_card_id ?? undefined)
watch(() => props.card.selected_ai_param_card_id, (id) => {
  selectedAiParamCardId.value = id ?? undefined
})

// 确保本地卡片与内容结构
const localCard = reactive({ 
  ...props.card,
  content: {
    content: '<p></p>',
    word_count: 0,
    ...(props.card.content as any || {})
  }
})

const editor = useEditor({
  content: localCard.content?.content || '<p></p>',
  extensions: [
    StarterKit.configure({ underline: false }),
    Underline,
    Highlight,
    TextAlign.configure({ types: ['heading', 'paragraph'] }),
  ],
})

const wordCount = ref(0)
const autoIndent = ref(false)
const aiLoading = ref(false)

// 外部卡片变更
watch(() => props.card, (newCard) => {
  Object.assign(localCard, newCard)
  const newContent = (newCard.content as any)?.content || '<p></p>'
  if (editor.value && editor.value.getHTML() !== newContent) {
    editor.value.commands.setContent(newContent)
  }
}, { deep: true })

// 编辑器内容变化同步
watch(() => editor.value?.getJSON(), () => {
  if (editor.value) {
    wordCount.value = editor.value.getText().length
    localCard.content = {
      ...(localCard.content || {}),
      content: editor.value.getJSON(),
      word_count: wordCount.value
    }
  }
})

function handleKeydown(event: KeyboardEvent) {
  if (autoIndent.value && event.key === 'Enter') {
    setTimeout(() => {
      if (autoIndent.value && editor.value) {
        editor.value.commands.insertContent('　　')
      }
    }, 10)
  }
}

function toggleAutoIndent() {
  autoIndent.value = !autoIndent.value
  ElMessage.info(`自动缩进已${autoIndent.value ? '开启' : '关闭'}`)
}

async function handleSave() {
  const updatePayload: CardUpdate = {
    title: localCard.title,
    content: {
      ...localCard.content,
      content: editor.value?.getJSON(),
      word_count: wordCount.value
    }
  }
  await cardStore.modifyCard(localCard.id, updatePayload)
}

function resolveLlmConfigId(): number | undefined {
  const selectedParamCard = aiParamCardStore.findByKey?.(selectedAiParamCardId.value)
  if (selectedParamCard?.llm_config_id) return selectedParamCard.llm_config_id
  // 回退：尝试使用第一个参数卡
  const first = (aiParamCardStore as any).paramCards?.[0]
  return first?.llm_config_id
}

async function executeAIContinuation() {
  if (!editor.value) return
  const llmConfigId = resolveLlmConfigId()
  if (!llmConfigId) {
    ElMessage.error('请先选择一个有效的AI参数配置（模型）')
    return
  }
  aiLoading.value = true

  const requestData: ContinuationRequest = {
    previous_content: editor.value.getText(),
    llm_config_id: llmConfigId,
    stream: true,
  }

  editor.value.commands.focus('end')

  generateContinuationStreaming(
    requestData,
    (chunk) => {
      if (chunk) editor.value?.commands.insertContent(chunk)
    },
    () => {
      aiLoading.value = false
      ElMessage.success('AI续写完成！')
    },
    (error) => {
      aiLoading.value = false
      console.error('AI续写失败:', error)
      ElMessage.error('AI续写失败')
    }
  )
}

onUnmounted(() => {
  editor.value?.destroy()
})
</script>

<style scoped>
/* 保持与原样式一致 */
.editor-container {
  border: 1px solid var(--el-border-color);
  border-radius: var(--el-border-radius-base);
  display: flex;
  flex-direction: column;
  height: 100%;
}

.toolbar {
  padding: 8px;
  border-bottom: 1px solid var(--el-border-color);
  background-color: var(--el-fill-color-lighter);
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.mx-2 {
  margin-left: 0.5rem;
  margin-right: 0.5rem;
}
.ml-2 {
  margin-left: 0.5rem;
}
.flex-spacer {
  flex-grow: 1;
}
.word-count-display {
  font-size: 14px;
  color: var(--el-text-color-regular);
  margin-right: 12px;
}
.editor-content-wrapper {
  flex-grow: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.chapter-title-display {
  padding: 20px 20px 10px 20px;
  border-bottom: 1px solid var(--el-border-color-light);
  background-color: var(--el-fill-color-lighter);
}
.chapter-title-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
}
.chapter-title-text {
  margin: 0;
  font-size: 24px;
  font-weight: bold;
}
.editor-content {
  flex-grow: 1;
  overflow-y: auto;
}
.editor-content :deep(.ProseMirror) {
  padding: 20px;
  min-height: 400px;
  outline: none;
  line-height: 1.8;
}
</style> 