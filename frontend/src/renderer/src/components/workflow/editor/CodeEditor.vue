<template>
  <div ref="editorRef" class="code-editor"></div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch, computed } from 'vue'
import { EditorState } from '@codemirror/state'
import { EditorView, keymap, lineNumbers } from '@codemirror/view'
import { defaultKeymap, history, historyKeymap } from '@codemirror/commands'
import { syntaxHighlighting, HighlightStyle } from '@codemirror/language'
import { python } from '@codemirror/lang-python'
import { tags } from '@lezer/highlight'

const props = defineProps({
  modelValue: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['update:modelValue', 'change'])

const editorRef = ref(null)
let view = null

// 检测暗黑模式
const isDark = computed(() => {
  if (typeof document !== 'undefined') {
    return document.documentElement.classList.contains('dark')
  }
  return false
})

// 创建主题
const createTheme = () => {
  const dark = isDark.value
  
  return EditorView.theme({
    "&": { 
      height: "100%", 
      fontSize: "14px",
      backgroundColor: dark ? '#1e1e1e' : '#ffffff'
    },
    ".cm-scroller": { 
      overflow: "auto",
      fontFamily: "'Monaco', 'Menlo', 'Courier New', monospace"
    },
    ".cm-content": {
      caretColor: dark ? '#ffffff' : '#000000',
      color: dark ? '#d4d4d4' : '#24292f'
    },
    ".cm-line": {
      color: dark ? '#d4d4d4' : '#24292f'
    },
    ".cm-gutters": {
      backgroundColor: dark ? '#252526' : '#f5f7fa',
      color: dark ? '#858585' : '#909399',
      border: 'none'
    },
    ".cm-activeLineGutter": {
      backgroundColor: dark ? '#2a2a2a' : '#e4e7ed'
    },
    ".cm-activeLine": {
      backgroundColor: dark ? 'rgba(255, 255, 255, 0.05)' : 'rgba(0, 0, 0, 0.02)'
    },
    ".cm-selectionBackground, ::selection": {
      backgroundColor: dark ? '#264f78' : '#add6ff'
    },
    ".cm-cursor": {
      borderLeftColor: dark ? '#ffffff' : '#000000'
    }
  }, { dark })
}

const createSyntaxHighlighting = () => {
  const dark = isDark.value

  const highlightStyle = HighlightStyle.define([
    { tag: tags.comment, color: dark ? '#6A9955' : '#008000', fontStyle: 'italic' },
    { tag: [tags.string, tags.special(tags.string)], color: dark ? '#CE9178' : '#A31515' },
    { tag: [tags.number, tags.float, tags.integer], color: dark ? '#B5CEA8' : '#098658' },
    { tag: [tags.bool, tags.null], color: dark ? '#569CD6' : '#0000FF', fontWeight: '600' },

    { tag: [tags.keyword, tags.controlKeyword, tags.operatorKeyword], color: dark ? '#C586C0' : '#AF00DB', fontWeight: '600' },

    { tag: tags.definition(tags.variableName), color: dark ? '#4FC1FF' : '#007ACC', fontWeight: '600' },
    { tag: tags.variableName, color: dark ? '#9CDCFE' : '#001080' },
    { tag: [tags.propertyName, tags.attributeName], color: dark ? '#4EC9B0' : '#795E26' },

    { tag: [tags.function(tags.variableName), tags.function(tags.propertyName)], color: dark ? '#DCDCAA' : '#795E26' },
    { tag: [tags.className, tags.typeName], color: dark ? '#4EC9B0' : '#267F99', fontWeight: '600' },

    { tag: [tags.operator, tags.punctuation], color: dark ? '#D4D4D4' : '#303133' }
  ])

  return syntaxHighlighting(highlightStyle, { fallback: true })
}

onMounted(() => {
  if (!editorRef.value) return

  const updateListener = EditorView.updateListener.of((update) => {
    if (update.docChanged) {
      const newValue = update.state.doc.toString()
      emit('update:modelValue', newValue)
      emit('change', newValue)
    }
  })

  const baseExtensions = [
    lineNumbers(),
    history(),
    keymap.of([...defaultKeymap, ...historyKeymap]),
    python(),
    createSyntaxHighlighting(),
    EditorView.lineWrapping,
    updateListener
  ]

  const startState = EditorState.create({
    doc: props.modelValue,
    extensions: [
      createTheme(),
      ...baseExtensions
    ]
  })

  view = new EditorView({
    state: startState,
    parent: editorRef.value
  })
  
  // 监听暗黑模式变化
  const observer = new MutationObserver(() => {
    if (view) {
      // 重新配置主题
      view.dispatch({
        effects: EditorView.reconfigure.of([
          createTheme(),
          ...baseExtensions
        ])
      })
    }
  })
  
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['class']
  })
  
  // 保存 observer 以便清理
  view._themeObserver = observer
})

watch(() => props.modelValue, (newValue) => {
  if (view && view.state.doc.toString() !== newValue) {
    view.dispatch({
      changes: { from: 0, to: view.state.doc.length, insert: newValue }
    })
  }
})

onBeforeUnmount(() => {
  if (view) {
    if (view._themeObserver) {
      view._themeObserver.disconnect()
    }
    view.destroy()
  }
})
</script>

<style scoped>
.code-editor {
  height: 100%;
  width: 100%;
  overflow: hidden;
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  background: var(--el-bg-color);
}
</style>
