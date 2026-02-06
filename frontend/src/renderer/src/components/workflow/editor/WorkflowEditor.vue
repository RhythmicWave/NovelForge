<template>
  <div class="workflow-editor">
    <div class="editor-header">
      <span class="editor-title">工作流代码</span>
      <el-tag type="info" size="small" v-if="isRunning">执行中...</el-tag>
    </div>
    <div ref="editorContainer" class="editor-container"></div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch, onBeforeUnmount } from 'vue'
import { EditorView, basicSetup } from 'codemirror'
import { EditorState } from '@codemirror/state'

const props = defineProps({
  modelValue: {
    type: String,
    default: ''
  },
  isRunning: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:modelValue', 'change', 'cursor-change'])

const editorContainer = ref(null)
let editorView = null

// 初始化编辑器
onMounted(() => {
  if (!editorContainer.value) return

  // 创建编辑器状态
  const startState = EditorState.create({
    doc: props.modelValue,
    extensions: [
      basicSetup,
      EditorView.updateListener.of((update) => {
        if (update.docChanged) {
          const newValue = update.state.doc.toString()
          emit('update:modelValue', newValue)
          emit('change', newValue)
        }
        // 监听光标位置变化
        if (update.selectionSet) {
          const line = update.state.doc.lineAt(update.state.selection.main.head)
          emit('cursor-change', line.number - 1) // 转换为0-based索引
        }
      }),
      EditorView.editable.of(!props.isRunning),
      EditorView.theme({
        '&': {
          height: '100%',
          fontSize: '14px'
        },
        '.cm-scroller': {
          fontFamily: "'Consolas', 'Monaco', 'Courier New', monospace",
          lineHeight: '1.6'
        },
        '.cm-content': {
          padding: '16px 0'
        },
        '.cm-line': {
          padding: '0 16px'
        }
      })
    ]
  })

  // 创建编辑器视图
  editorView = new EditorView({
    state: startState,
    parent: editorContainer.value
  })
})

// 监听外部值变化
watch(() => props.modelValue, (newValue) => {
  if (editorView && editorView.state.doc.toString() !== newValue) {
    editorView.dispatch({
      changes: {
        from: 0,
        to: editorView.state.doc.length,
        insert: newValue
      }
    })
  }
})

// 监听运行状态变化
watch(() => props.isRunning, (isRunning) => {
  if (editorView) {
    // 重新创建编辑器状态来改变可编辑性
    const currentDoc = editorView.state.doc.toString()
    const newState = EditorState.create({
      doc: currentDoc,
      extensions: [
        basicSetup,
        EditorView.updateListener.of((update) => {
          if (update.docChanged) {
            const newValue = update.state.doc.toString()
            emit('update:modelValue', newValue)
            emit('change', newValue)
          }
        }),
        EditorView.editable.of(!isRunning),
        EditorView.theme({
          '&': {
            height: '100%',
            fontSize: '14px'
          },
          '.cm-scroller': {
            fontFamily: "'Consolas', 'Monaco', 'Courier New', monospace",
            lineHeight: '1.6'
          },
          '.cm-content': {
            padding: '16px 0'
          },
          '.cm-line': {
            padding: '0 16px'
          }
        })
      ]
    })
    editorView.setState(newState)
  }
})

// 清理
onBeforeUnmount(() => {
  if (editorView) {
    editorView.destroy()
  }
})
</script>

<style scoped>
.workflow-editor {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: white;
}

.editor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  border-bottom: 1px solid #ebeef5;
  background: #f8f9fa;
}

.editor-title {
  font-size: 14px;
  font-weight: 600;
  color: #606266;
}

.editor-container {
  flex: 1;
  overflow: auto;
  background: #fafafa;
}

.editor-container :deep(.cm-editor) {
  height: 100%;
}

.editor-container :deep(.cm-scroller) {
  overflow: auto;
}
</style>
