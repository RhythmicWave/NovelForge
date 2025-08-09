import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'

export const useEditorStore = defineStore('editor', () => {
  // 当前激活的编辑器
  const activeEditor = ref<{ type: string; id: string; data?: any } | null>(null)
  
  // 侧栏宽度
  const leftSidebarWidth = ref(250)
  const rightSidebarWidth = ref(300)
  
  // 侧栏宽度限制
  const minLeftWidth = 180
  const maxLeftWidth = 400
  const minRightWidth = 220
  const maxRightWidth = 500
  
  // 导航树展开状态
  const expandedKeys = ref<string[]>(['content-root'])
  
  // 右键菜单状态
  const contextMenu = reactive({
    visible: false,
    x: 0,
    y: 0,
    items: [] as { label: string; action: () => void }[],
    nodeData: null as any | null
  })
  
  // AI配置对话框状态
  const aiConfigDialog = reactive({
    visible: false,
    task: '',
    input: {} as any
  })
  
  // 拖拽调整状态
  const resizing = ref<'left' | 'right' | null>(null)
  let startX = 0
  let startWidth = 0

  // Actions
  function setActiveEditor(editor: { type: string; id: string; data?: any } | null) {
    activeEditor.value = editor
  }

  function setLeftSidebarWidth(width: number) {
    leftSidebarWidth.value = Math.max(minLeftWidth, Math.min(maxLeftWidth, width))
  }

  function setRightSidebarWidth(width: number) {
    rightSidebarWidth.value = Math.max(minRightWidth, Math.min(maxRightWidth, width))
  }

  function addExpandedKey(key: string) {
    if (!expandedKeys.value.includes(key)) {
      expandedKeys.value.push(key)
    }
  }

  function removeExpandedKey(key: string) {
    const index = expandedKeys.value.indexOf(key)
    if (index !== -1) {
      expandedKeys.value.splice(index, 1)
    }
  }

  function setExpandedKeys(keys: string[]) {
    expandedKeys.value = keys
  }

  function showContextMenu(x: number, y: number, items: { label: string; action: () => void }[], nodeData?: any) {
    contextMenu.x = x
    contextMenu.y = y
    contextMenu.items = items
    contextMenu.nodeData = nodeData || null
    contextMenu.visible = true
  }

  function hideContextMenu() {
    contextMenu.visible = false
  }

  function showAIConfigDialog(task: string, input: any) {
    aiConfigDialog.task = task
    aiConfigDialog.input = input
    aiConfigDialog.visible = true
  }

  function hideAIConfigDialog() {
    aiConfigDialog.visible = false
  }

  function startResizing(side: 'left' | 'right') {
    resizing.value = side
    startX = window.event instanceof MouseEvent ? window.event.clientX : 0
    startWidth = side === 'left' ? leftSidebarWidth.value : rightSidebarWidth.value
    document.body.style.cursor = 'col-resize'
    window.addEventListener('mousemove', handleResizing)
    window.addEventListener('mouseup', stopResizing)
  }

  function handleResizing(e: MouseEvent) {
    if (!resizing.value) return
    if (resizing.value === 'left') {
      let newWidth = startWidth + (e.clientX - startX)
      setLeftSidebarWidth(newWidth)
    } else if (resizing.value === 'right') {
      let newWidth = startWidth - (e.clientX - startX)
      setRightSidebarWidth(newWidth)
    }
  }

  function stopResizing() {
    resizing.value = null
    document.body.style.cursor = ''
    window.removeEventListener('mousemove', handleResizing)
    window.removeEventListener('mouseup', stopResizing)
  }

  function reset() {
    activeEditor.value = null
    leftSidebarWidth.value = 250
    rightSidebarWidth.value = 300
    expandedKeys.value = ['content-root']
    contextMenu.visible = false
    aiConfigDialog.visible = false
    resizing.value = null
  }

  return {
    // State
    activeEditor,
    leftSidebarWidth,
    rightSidebarWidth,
    minLeftWidth,
    maxLeftWidth,
    minRightWidth,
    maxRightWidth,
    expandedKeys,
    contextMenu,
    aiConfigDialog,
    resizing,
    
    // Actions
    setActiveEditor,
    setLeftSidebarWidth,
    setRightSidebarWidth,
    addExpandedKey,
    removeExpandedKey,
    setExpandedKeys,
    showContextMenu,
    hideContextMenu,
    showAIConfigDialog,
    hideAIConfigDialog,
    startResizing,
    handleResizing,
    stopResizing,
    reset
  }
}) 