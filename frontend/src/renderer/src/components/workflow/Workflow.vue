<template>
  <div class="workflow-container">
    <!-- 顶部工具栏 -->
    <div class="workflow-toolbar">
      <div class="toolbar-left">
        <el-select
          v-model="currentWorkflowId"
          placeholder="选择工作流"
          filterable
          clearable
          @change="onWorkflowChange"
          style="width: 300px"
        >
          <el-option
            v-for="wf in workflowList"
            :key="wf.id"
            :label="wf.name"
            :value="wf.id"
          >
            <span style="float: left">{{ wf.name }}</span>
            <span style="float: right; color: #8492a6; font-size: 13px">
              {{ formatDate(wf.updated_at) }}
            </span>
          </el-option>
        </el-select>

        <el-button @click="createNewWorkflow">
          <el-icon><Plus /></el-icon>
          <span>新建</span>
        </el-button>
        
        <el-button 
          @click="deleteWorkflow" 
          :disabled="!currentWorkflowId"
          type="danger"
          plain
        >
          <el-icon><Delete /></el-icon>
          <span>删除</span>
        </el-button>
      </div>

      <div class="toolbar-right">
        <div class="toolbar-switch-item">
          <span class="switch-label">持久化保存</span>
          <el-switch
            v-model="keepRunHistory"
            @change="onKeepRunHistoryChange"
            :disabled="!currentWorkflowId"
            size="small"
          />
        </div>
        
        <el-divider direction="vertical" />
        
        <el-button 
          @click="showRunsDialog = true"
          plain
        >
          <el-icon><Clock /></el-icon>
          <span>运行记录</span>
        </el-button>
        
        <el-button 
          @click="validateWorkflowCode" 
          :disabled="!currentWorkflowId"
          plain
        >
          <el-icon><CircleCheck /></el-icon>
          <span>校验代码</span>
        </el-button>
        
        <el-divider direction="vertical" />
        
        <el-button @click="saveWorkflow">
          <el-icon><Document /></el-icon>
          <span>保存</span>
        </el-button>
        
        <el-divider direction="vertical" />
        
        <el-button
          v-if="canStart"
          @click="runWorkflow"
          type="primary"
        >
          <el-icon><VideoPlay /></el-icon>
          <span>执行</span>
        </el-button>
        <el-button
          v-if="canPause"
          @click="pauseCurrentRun"
          type="warning"
        >
          <el-icon><VideoPause /></el-icon>
          <span>暂停</span>
        </el-button>
        <el-button
          v-if="canResume"
          @click="resumeCurrentRun"
          type="success"
        >
          <el-icon><VideoPlay /></el-icon>
          <span>恢复</span>
        </el-button>
      </div>
    </div>

    <!-- 主内容区 -->
    <div class="workflow-content">
      <!-- 节点库 -->
      <div class="library-section" :style="{ width: libraryWidth + 'px' }">
        <node-library @add-node="onAddNode" />
      </div>

      <!-- 拖动条 - 节点库 -->
      <div class="resize-handle" @mousedown="startResizing('library')"></div>

      <!-- 节点块编辑器 -->
      <div class="editor-section">
        <div class="section-header">
          <span class="section-title">工作流节点</span>
          <span class="section-subtitle" v-if="currentWorkflowName">
            {{ currentWorkflowName }}
          </span>
          <div class="view-mode-toggle" style="margin-left: auto">
             <el-radio-group v-model="viewMode" size="small">
                <el-radio-button label="visual">
                   <el-icon><List /></el-icon> 可视化
                </el-radio-button>
                <el-radio-button label="code">
                   <el-icon><Document /></el-icon> 代码
                </el-radio-button>
             </el-radio-group>
          </div>
        </div>
        <div style="flex: 1; overflow: hidden; position: relative">
            <node-block-editor
              v-if="viewMode === 'visual'"
              v-model="code"
              :is-running="isRunning"
            />
            <code-editor
              v-else
              v-model="code"
            />
        </div>
      </div>

      <!-- 拖动条 - Notebook -->
      <div class="resize-handle" @mousedown="startResizing('notebook')"></div>

      <!-- Notebook执行视图 -->
      <div class="notebook-section" :style="{ width: notebookWidth + 'px' }">
        <workflow-notebook
          :cells="notebookCells"
          :is-running="isRunning"
          @cell-output="onCellOutput"
          @clear-output="clearOutput"
        />
      </div>
    </div>

    <!-- 运行记录对话框 -->
    <workflow-runs-dialog 
      v-model="showRunsDialog" 
      :workflow-id="currentWorkflowId"
      @resume-run="onResumeRun"
    />

    <!-- 校验结果对话框 -->
    <el-dialog
      v-model="showValidationDialog"
      title="工作流校验结果"
      width="600px"
    >
      <div v-if="validationResult">
        <el-alert
          :type="validationResult.is_valid ? 'success' : 'error'"
          :title="validationResult.is_valid ? '校验通过' : '校验失败'"
          :closable="false"
          style="margin-bottom: 16px"
        >
          <template v-if="!validationResult.is_valid">
            发现 {{ validationResult.errors.length }} 个错误
            <span v-if="validationResult.warnings.length > 0">
              和 {{ validationResult.warnings.length }} 个警告
            </span>
          </template>
        </el-alert>

        <!-- 错误列表 -->
        <div v-if="validationResult.errors.length > 0" style="margin-bottom: 16px">
          <h4 style="margin-bottom: 8px; color: #f56c6c">错误</h4>
          <el-scrollbar max-height="300px">
            <div
              v-for="(error, index) in validationResult.errors"
              :key="'error-' + index"
              class="validation-item error-item"
            >
              <div class="validation-header">
                <el-tag type="danger" size="small">{{ error.error_type }}</el-tag>
                <span class="validation-location">行 {{ error.line }}</span>
                <span v-if="error.variable" class="validation-variable">{{ error.variable }}</span>
              </div>
              <div class="validation-message">{{ error.message }}</div>
              <div v-if="error.suggestion" class="validation-suggestion">
                💡 {{ error.suggestion }}
              </div>
            </div>
          </el-scrollbar>
        </div>

        <!-- 警告列表 -->
        <div v-if="validationResult.warnings.length > 0">
          <h4 style="margin-bottom: 8px; color: #e6a23c">警告</h4>
          <el-scrollbar max-height="200px">
            <div
              v-for="(warning, index) in validationResult.warnings"
              :key="'warning-' + index"
              class="validation-item warning-item"
            >
              <div class="validation-header">
                <el-tag type="warning" size="small">{{ warning.error_type }}</el-tag>
                <span class="validation-location">行 {{ warning.line }}</span>
                <span v-if="warning.variable" class="validation-variable">{{ warning.variable }}</span>
              </div>
              <div class="validation-message">{{ warning.message }}</div>
              <div v-if="warning.suggestion" class="validation-suggestion">
                💡 {{ warning.suggestion }}
              </div>
            </div>
          </el-scrollbar>
        </div>
      </div>

      <template #footer>
        <el-button @click="showValidationDialog = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, Document, Delete, VideoPlay, VideoPause, Close, List, Clock, CircleCheck, ArrowDown } from '@element-plus/icons-vue'
import NodeBlockEditor from './editor/NodeBlockEditor.vue'
import CodeEditor from './editor/CodeEditor.vue'
import WorkflowNotebook from './notebook/WorkflowNotebook.vue'
import NodeLibrary from './panels/NodeLibrary.vue'
import WorkflowRunsDialog from './dialogs/WorkflowRunsDialog.vue'
import { useWorkflowExecution } from '@/composables/useWorkflowExecution'
import { useWorkflowProgress } from '@/composables/useWorkflowProgress'
import {
  listWorkflows,
  saveCodeWorkflow,
  getCodeWorkflow,
  updateWorkflow,
  deleteWorkflow as deleteWorkflowApi,
  validateWorkflow
} from '@/api/workflows'
import request from '@/api/request'

// 使用状态机管理执行状态
const {
  execution,
  isRunning,
  isPaused,
  isIdle,
  canPause,
  canResume,
  canStart,
  start: startExecution,
  updateRunId,
  pause: pauseExecution,
  resume: resumeExecution,
  complete: completeExecution,
  fail: failExecution,
  reset: resetExecution
} = useWorkflowExecution()

// 使用进度管理
const { startWorkflow, pauseWorkflow } = useWorkflowProgress()

const code = ref(``)
const showRunsDialog = ref(false)
const showValidationDialog = ref(false)
const validationResult = ref(null)

const viewMode = ref('visual') // 'visual' | 'code'
const notebookCells = reactive([])
let currentWorkflowId = ref(null) // 当前工作流ID
let currentWorkflowName = ref('未命名工作流') // 当前工作流名称
const keepRunHistory = ref(false) // 是否持久化保存运行记录
const workflowList = ref([]) // 工作流列表

// 拖动调整宽度
const libraryWidth = ref(280)
const notebookWidth = ref(500)
const minLibraryWidth = 200
const maxLibraryWidth = 500
const minNotebookWidth = 300
const maxNotebookWidth = 800
let resizingPanel = ref(null)
let startX = 0
let startWidth = 0

function startResizing(panel) {
  resizingPanel.value = panel
  startX = window.event.clientX
  startWidth = panel === 'library' ? libraryWidth.value : notebookWidth.value
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  window.addEventListener('mousemove', handleResizing)
  window.addEventListener('mouseup', stopResizing)
}

function handleResizing(e) {
  if (!resizingPanel.value) return
  
  if (resizingPanel.value === 'library') {
    let newWidth = startWidth + (e.clientX - startX)
    newWidth = Math.max(minLibraryWidth, Math.min(maxLibraryWidth, newWidth))
    libraryWidth.value = newWidth
  } else if (resizingPanel.value === 'notebook') {
    let newWidth = startWidth - (e.clientX - startX)
    newWidth = Math.max(minNotebookWidth, Math.min(maxNotebookWidth, newWidth))
    notebookWidth.value = newWidth
  }
}

function stopResizing() {
  resizingPanel.value = null
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  window.removeEventListener('mousemove', handleResizing)
  window.removeEventListener('mouseup', stopResizing)
}

// 加载工作流列表
const loadWorkflowList = async () => {
  try {
    const workflows = await listWorkflows()
    // 所有工作流都是代码式工作流（dsl_version === 2）
    workflowList.value = workflows.filter(wf => {
      return wf.dsl_version === 2
    })
  } catch (error) {
    console.error('[Workflow] 加载工作流列表失败:', error)
    ElMessage.error('加载工作流列表失败')
  }
}

// 刷新工作流列表
const refreshWorkflowList = async () => {
  await loadWorkflowList()
  ElMessage.success('工作流列表已刷新')
}

// 工作流切换
const onWorkflowChange = async (workflowId) => {
  if (!workflowId) {
    // 清空选择
    currentWorkflowId.value = null
    currentWorkflowName.value = '未命名工作流'
    code.value = `# 示例工作流
project = Logic.SelectProject(project_id=1)
novel = Novel.Load(root_path="E:\\\\Novels\\\\book")
cards = Card.BatchUpsert(
    items=novel.volume_list,
    card_type="volume",
    title_template="{item}"
)`
    notebookCells.length = 0
    return
  }

  try {
    const workflow = await getCodeWorkflow(workflowId)
    currentWorkflowId.value = workflow.id
    currentWorkflowName.value = workflow.name
    code.value = workflow.code || ''
    keepRunHistory.value = workflow.keep_run_history || false // 加载持久化设置
    notebookCells.length = 0 // 清空输出
  } catch (error) {
    console.error('[Workflow] 加载工作流失败:', error)
    ElMessage.error('加载工作流失败')
  }
}

// 创建新工作流
const createNewWorkflow = async () => {
  try {
    const { value: name } = await ElMessageBox.prompt('请输入工作流名称', '新建工作流', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputValue: '新工作流',
      inputPattern: /\S+/,
      inputErrorMessage: '工作流名称不能为空',
      inputValidator: (value) => {
        if (!value || !value.trim()) {
          return '工作流名称不能为空'
        }
        // 检查是否重名
        const exists = workflowList.value.some(wf => wf.name === value.trim())
        if (exists) {
          return '工作流名称已存在，请使用其他名称'
        }
        return true
      }
    })

    // 创建新工作流，使用空代码模板
    const initialCode = '# 新工作流\n'
    const workflow = await saveCodeWorkflow(name, initialCode)
    currentWorkflowId.value = workflow.id
    currentWorkflowName.value = workflow.name
    code.value = initialCode  // 更新代码

    // 刷新列表
    await loadWorkflowList()

    ElMessage.success(`工作流"${workflow.name}"已创建`)
  } catch (error) {
    if (error !== 'cancel') {
      console.error('[Workflow] 创建工作流失败:', error)
      ElMessage.error('创建工作流失败')
    }
  }
}

// 删除工作流
const deleteWorkflow = async () => {
  if (!currentWorkflowId.value) {
    ElMessage.warning('请先选择要删除的工作流')
    return
  }

  try {
    await ElMessageBox.confirm(
      `确定要删除工作流"${currentWorkflowName.value}"吗？此操作不可恢复。`,
      '删除工作流',
      {
        confirmButtonText: '确定删除',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    // 删除工作流
    await deleteWorkflowApi(currentWorkflowId.value)

    // 清空当前选择
    currentWorkflowId.value = null
    currentWorkflowName.value = '未命名工作流'
    code.value = `# 示例工作流
project = Logic.SelectProject(project_id=1)
novel = Novel.Load(root_path="E:\\\\Novels\\\\book")
cards = Card.BatchUpsert(
    items=novel.volume_list,
    card_type="volume",
    title_template="{item}"
)`
    notebookCells.length = 0

    // 刷新列表
    await loadWorkflowList()

    ElMessage.success('工作流已删除')
  } catch (error) {
    if (error !== 'cancel') {
      console.error('[Workflow] 删除工作流失败:', error)
      ElMessage.error('删除工作流失败')
    }
  }
}

// 格式化日期
const formatDate = (dateStr) => {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  const now = new Date()
  const diff = now - date

  // 小于1分钟
  if (diff < 60000) return '刚刚'
  // 小于1小时
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
  // 小于1天
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`
  // 小于7天
  if (diff < 604800000) return `${Math.floor(diff / 86400000)}天前`

  // 超过7天显示日期
  return date.toLocaleDateString('zh-CN')
}

// 持久化开关变更
const onKeepRunHistoryChange = async (value) => {
  if (!currentWorkflowId.value) return
  
  try {
    await updateWorkflow(currentWorkflowId.value, {
      keep_run_history: value
    })
    ElMessage.success(value ? '已开启运行记录持久化' : '已关闭运行记录持久化')
  } catch (error) {
    console.error('[Workflow] 更新持久化设置失败:', error)
    ElMessage.error('更新持久化设置失败')
    // 恢复原值
    keepRunHistory.value = !value
  }
}

// 执行工作流
const runWorkflow = async () => {
  if (!canStart.value) return

  notebookCells.length = 0 // 清空之前的输出

  try {
    // 1. 每次执行都重新保存工作流（确保代码是最新的）
    if (currentWorkflowId.value) {
      // 更新现有工作流
      await updateWorkflow(currentWorkflowId.value, {
        definition_code: code.value
      })
    } else {
      // 创建新工作流
      const workflow = await saveCodeWorkflow(currentWorkflowName.value, code.value)
      currentWorkflowId.value = workflow.id
    }

    // 2. 执行工作流
    // 使用全局 SSE 连接管理（自动更新状态栏）
    await startWorkflow(
      currentWorkflowId.value,
      currentWorkflowName.value,
      {
        onRunStarted: (actualRunId) => {
          // 更新状态机中的 runId（不改变状态）
          updateRunId(actualRunId)
        },
        onStart: (event) => {
          notebookCells.push({
            id: event.statement?.variable || 'unknown',
            type: 'execution',
            content: event.statement?.code || '',
            status: 'running',
            outputs: []
          })
        },
        onProgress: (event) => {
          const cellIndex = notebookCells.findIndex(c => c.id === event.statement?.variable)
          if (cellIndex !== -1) {
            // 使用 splice 来强制触发响应式更新
            const updatedCell = {
              ...notebookCells[cellIndex],
              status: 'progress',
              progress: event.percent,
              message: event.message
            }
            notebookCells.splice(cellIndex, 1, updatedCell)
          }
        },
        onComplete: (event) => {
          const cellIndex = notebookCells.findIndex(c => c.id === event.statement?.variable)
          if (cellIndex !== -1) {
            notebookCells[cellIndex] = {
              ...notebookCells[cellIndex],
              status: 'completed',
              outputs: [event.result],
              resumed: event.resumed || false  // 标记是否是恢复的节点
            }
          } else {
            // 如果 cell 不存在（恢复的节点），创建一个
            notebookCells.push({
              id: event.statement?.variable || 'unknown',
              type: 'execution',
              content: event.statement?.code || '',
              status: 'completed',
              outputs: [event.result],
              resumed: true  // 标记为恢复的节点
            })
          }
        },
        onError: (event) => {
          const cell = notebookCells.find(c => c.id === event.statement?.variable)
          if (cell) {
            cell.status = 'error'
            cell.error = event.error
          } else {
            // 没有对应的 cell（比如解析失败），创建一个错误 cell
            notebookCells.push({
              id: 'error-' + Date.now(),
              type: 'execution',
              content: event.statement?.code || '代码解析失败',
              status: 'error',
              error: event.error || '未知错误',
              outputs: []
            })
          }
          // 标记为失败状态
          failExecution(event.error || '工作流执行失败')
          ElMessage.error(event.error || '工作流执行失败')
        },
        onEnd: () => {
          // 如果不是失败状态，标记为完成
          if (execution.state === 'running') {
            completeExecution()
          }
        }
      },
      false // resume=false，从头开始
    )
    
    // 初始状态转换（使用临时 runId 0）
    // 真实的 runId 会在 onRunStarted 回调中更新
    startExecution(currentWorkflowId.value, 0)
  } catch (error) {
    console.error('[Workflow] 工作流执行失败:', error)
    failExecution(error.message || '工作流执行失败')
    ElMessage.error(error.message || '工作流执行失败')
  }
}

// 清空输出
const clearOutput = () => {
  notebookCells.length = 0
  // 重置状态机
  if (!isIdle.value) {
    resetExecution()
  }
}

// 暂停当前运行
const pauseCurrentRun = async () => {
  if (!canPause.value) return
  
  if (execution.runId === null || execution.runId === undefined) {
    console.error('[Workflow] 无法暂停：缺少 runId')
    return
  }
  
  try {
    console.log('[Workflow] 开始暂停工作流:', execution.runId)
    
    // 1. 先通过 store 关闭 SSE 连接（停止接收事件）
    pauseWorkflow(execution.runId)
    
    // 2. 调用 pause API 更新数据库状态（后端会停止执行）
    await request.post(`/workflows/runs/${execution.runId}/pause`, {}, '/api')
    
    // 3. 状态机转换到暂停状态
    pauseExecution()
    
    console.log('[Workflow] 工作流已暂停')
    ElMessage.success('工作流已暂停')
  } catch (error) {
    console.error('[Workflow] 暂停失败:', error)
    ElMessage.error(`暂停失败：${error.message || error}`)
  }
}

// 恢复当前运行
const resumeCurrentRun = async () => {
  if (!canResume.value) return
  
  if (execution.runId === null || execution.runId === undefined || execution.workflowId === null || execution.workflowId === undefined) {
    console.error('[Workflow] 无法恢复：缺少 runId 或 workflowId')
    return
  }
  
  try {
    // 清空之前的输出（避免重复显示）
    notebookCells.length = 0
    
    // 恢复执行：传递 resume=true 和 run_id
    await startWorkflow(
      execution.workflowId,
      currentWorkflowName.value,
      {
        onStart: (event) => {
          notebookCells.push({
            id: event.statement?.variable || 'unknown',
            type: 'execution',
            content: event.statement?.code || '',
            status: 'running',
            outputs: []
          })
        },
        onProgress: (event) => {
          const cellIndex = notebookCells.findIndex(c => c.id === event.statement?.variable)
          if (cellIndex !== -1) {
            const updatedCell = {
              ...notebookCells[cellIndex],
              status: 'progress',
              progress: event.percent,
              message: event.message
            }
            notebookCells.splice(cellIndex, 1, updatedCell)
          }
        },
        onComplete: (event) => {
          const cellIndex = notebookCells.findIndex(c => c.id === event.statement?.variable)
          if (cellIndex !== -1) {
            notebookCells[cellIndex] = {
              ...notebookCells[cellIndex],
              status: 'completed',
              outputs: [event.result],
              resumed: event.resumed || false
            }
          } else {
            // 如果 cell 不存在（恢复的节点），创建一个
            notebookCells.push({
              id: event.statement?.variable || 'unknown',
              type: 'execution',
              content: event.statement?.code || '',
              status: 'completed',
              outputs: [event.result],
              resumed: true
            })
          }
        },
        onError: (event) => {
          const cell = notebookCells.find(c => c.id === event.statement?.variable)
          if (cell) {
            cell.status = 'error'
            cell.error = event.error
          } else {
            notebookCells.push({
              id: 'error-' + Date.now(),
              type: 'execution',
              content: event.statement?.code || '代码解析失败',
              status: 'error',
              error: event.error || '未知错误',
              outputs: []
            })
          }
          // 标记为失败状态
          failExecution(event.error || '工作流执行失败')
          ElMessage.error(event.error || '工作流执行失败')
        },
        onEnd: () => {
          // 如果不是失败状态，标记为完成
          if (execution.state === 'running') {
            completeExecution()
          }
        }
      },
      true, // resume=true
      execution.runId // 传递 run_id
    )
    
    // 状态机转换到运行状态
    resumeExecution()
    
    ElMessage.success('工作流已恢复执行')
  } catch (error) {
    console.error('[Workflow] 恢复执行失败:', error)
    failExecution(error.message || '恢复执行失败')
    ElMessage.error(error.message || '恢复执行失败')
  }
}

// 取消当前运行
const cancelCurrentRun = async () => {
  if (!currentRunId.value) return
  
  try {
    await ElMessageBox.confirm('确定要取消当前工作流运行吗？', '确认取消', {
      type: 'warning'
    })
    
    await request.post(`/workflows/runs/${currentRunId.value}/cancel`, {}, '/api')
    ElMessage.success('工作流已取消')
    
    isRunning.value = false
    isPaused.value = false
    currentRunId.value = null
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(`取消失败：${error.message || error}`)
    }
  }
}

// 保存工作流
const saveWorkflow = async () => {
  try {
    if (currentWorkflowId.value) {
      // 更新现有工作流
      await updateWorkflow(currentWorkflowId.value, {
        definition_code: code.value
      })
      ElMessage.success('工作流已更新')
    } else {
      // 创建新工作流，先询问名称
      const { value: name } = await ElMessageBox.prompt('请输入工作流名称', '保存工作流', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputValue: currentWorkflowName.value,
        inputPattern: /\S+/,
        inputErrorMessage: '工作流名称不能为空'
      })

      // 保存代码式工作流
      const workflow = await saveCodeWorkflow(name, code.value)
      currentWorkflowId.value = workflow.id
      currentWorkflowName.value = workflow.name
      ElMessage.success(`工作流"${workflow.name}"已保存`)
    }
  } catch (error) {
    if (error !== 'cancel') {
      console.error('[Workflow] 保存工作流失败:', error)
      ElMessage.error(error.message || '保存工作流失败')
    }
  }
}

// 校验工作流
const validateWorkflowCode = async () => {
  if (!currentWorkflowId.value) {
    ElMessage.warning('请先选择或保存工作流')
    return
  }

  try {
    const result = await validateWorkflow(currentWorkflowId.value)
    validationResult.value = result
    showValidationDialog.value = true

    if (result.is_valid) {
      ElMessage.success('校验通过！')
    } else {
      ElMessage.error(`发现 ${result.errors.length} 个错误`)
    }
  } catch (error) {
    console.error('校验工作流失败:', error)
    ElMessage.error('校验工作流失败')
  }
}

// 代码变化处理
const onCodeChange = (newCode) => {
  code.value = newCode
}

// 节点选中处理
// const onNodeSelected = (node) => {
//   selectedNode.value = node
// }

// 节点更新处理（来自属性面板）
const onNodeUpdate = (updatedNode) => {
  // 重新生成代码
  // 需要找到对应的节点并替换其代码
  const lines = code.value.split('\n')

  // 简单实现：找到包含该变量名的行并替换
  // 更好的实现应该在 NodeBlockEditor 中维护节点列表
  let updated = false
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].includes(`${updatedNode.variable} =`)) {
      lines[i] = updatedNode.code
      updated = true
      break
    }
  }

  if (updated) {
    code.value = lines.join('\n')
    ElMessage.success('节点已更新')
  } else {
    ElMessage.error('更新失败：未找到对应节点')
  }
}

// 添加节点（来自节点库）
const onAddNode = (nodeType) => {
  // 生成唯一的变量名
  const baseName = generateVariableName(nodeType)
  const variableName = generateUniqueVariableName(baseName)

  // 生成 XML 格式的节点代码
  const nodeCode = `<node name="${variableName}">
  ${nodeType}()
</node>`

  // 添加到代码末尾
  const newCode = code.value.trim()
  if (newCode) {
    code.value = newCode + '\n\n' + nodeCode  // 使用双换行分隔
  } else {
    code.value = nodeCode
  }

  ElMessage.success('节点已添加')
}

// 根据节点类型生成基础变量名
function generateVariableName(nodeType) {
  // 提取节点类型名并转换为合适的变量名
  const parts = nodeType.split('.')
  if (parts.length >= 2) {
    const method = parts[1].toLowerCase()
    // 移除常见的动词前缀
    const cleanMethod = method.replace(/^(get|set|create|update|delete|fetch|load)_?/, '')
    return cleanMethod || method
  }
  return nodeType.replace(/\./g, '_').toLowerCase()
}

// 生成唯一的变量名
function generateUniqueVariableName(baseName) {
  let counter = 2
  let variableName = baseName

  // 检查是否已存在同名变量
  const allLines = code.value.split('\n')
  const usedVariables = new Set()

  allLines.forEach(line => {
    // 匹配 XML 格式：<node name="variable">
    const xmlMatch = line.match(/<node\s+name="(\w+)"/)
    if (xmlMatch) {
      usedVariables.add(xmlMatch[1])
    }
    
    // 兼容旧格式：variable = ...（如果还有遗留代码）
    const oldMatch = line.match(/^(\w+)\s*=\s*/)
    if (oldMatch) {
      usedVariables.add(oldMatch[1])
    }
  })

  // 如果基础名已存在，添加数字后缀
  while (usedVariables.has(variableName)) {
    variableName = `${baseName}${counter++}`
  }

  return variableName
}

// 单元格输出处理
const onCellOutput = (output) => {
  // 处理单元格输出
}

// 从运行记录恢复执行
const onResumeRun = async (run) => {
  // 清空之前的输出
  notebookCells.length = 0
  
  // 加载工作流代码
  let workflowData
  try {
    workflowData = await getCodeWorkflow(run.workflow_id)
    code.value = workflowData.code || ''
    currentWorkflowName.value = workflowData.name
    currentWorkflowId.value = run.workflow_id
  } catch (error) {
    console.error('[Workflow] 加载工作流失败:', error)
    ElMessage.error('加载工作流失败')
    return
  }
  
  try {
    await startWorkflow(
      run.workflow_id,
      workflowData.name,  // 使用 workflowData.name
      {
        onStart: (event) => {
          notebookCells.push({
            id: event.statement?.variable || 'unknown',
            type: 'execution',
            content: event.statement?.code || '',
            status: 'running',
            outputs: []
          })
        },
        onProgress: (event) => {
          const cellIndex = notebookCells.findIndex(c => c.id === event.statement?.variable)
          if (cellIndex !== -1) {
            const updatedCell = {
              ...notebookCells[cellIndex],
              status: 'progress',
              progress: event.percent,
              message: event.message
            }
            notebookCells.splice(cellIndex, 1, updatedCell)
          }
        },
        onComplete: (event) => {
          const cellIndex = notebookCells.findIndex(c => c.id === event.statement?.variable)
          if (cellIndex !== -1) {
            notebookCells[cellIndex] = {
              ...notebookCells[cellIndex],
              status: 'completed',
              outputs: [event.result],
              resumed: event.resumed || false
            }
          } else {
            // 如果 cell 不存在（恢复的节点），创建一个
            notebookCells.push({
              id: event.statement?.variable || 'unknown',
              type: 'execution',
              content: event.statement?.code || '',
              status: 'completed',
              outputs: [event.result],
              resumed: true
            })
          }
        },
        onError: (event) => {
          const cell = notebookCells.find(c => c.id === event.statement?.variable)
          if (cell) {
            cell.status = 'error'
            cell.error = event.error
          } else {
            notebookCells.push({
              id: 'error-' + Date.now(),
              type: 'execution',
              content: event.statement?.code || '代码解析失败',
              status: 'error',
              error: event.error || '未知错误',
              outputs: []
            })
          }
          // 标记为失败状态
          failExecution(event.error || '工作流执行失败')
          ElMessage.error(event.error || '工作流执行失败')
        },
        onEnd: () => {
          // 如果不是失败状态，标记为完成
          if (execution.state === 'running') {
            completeExecution()
          }
        }
      },
      true, // resume=true
      run.id // 传递 run_id
    )
    
    // 状态机转换到运行状态
    startExecution(run.workflow_id, run.id)
  } catch (error) {
    console.error('[Workflow] 恢复执行失败:', error)
    failExecution(error.message || '恢复执行失败')
    ElMessage.error(error.message || '恢复执行失败')
  }
}

// 组件卸载时清理
onUnmounted(() => {
  // SSE 连接由 store 管理，组件卸载时不需要手动清理
})

// 组件挂载时加载工作流列表
onMounted(() => {
  loadWorkflowList()
})
</script>

<style scoped>
.workflow-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--el-bg-color-page);
}

.workflow-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 20px;
  background: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color);
  box-shadow: 0 1px 4px var(--el-box-shadow-light);
}

.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.toolbar-switch-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 12px;
  height: 32px;
  border-radius: 4px;
  background: var(--el-fill-color-light);
}

.switch-label {
  font-size: 14px;
  color: var(--el-text-color-regular);
  white-space: nowrap;
}

.dropdown-switch-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px;
  min-width: 180px;
}

.switch-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: var(--el-text-color-regular);
}

.workflow-content {
  display: flex;
  flex: 1;
  overflow: hidden;
  gap: 0;
  background: var(--el-border-color-lighter);
  position: relative;
}

.library-section {
  display: flex;
  flex-direction: column;
  background: var(--el-bg-color);
  overflow: hidden;
  flex-shrink: 0;
}

.resize-handle {
  width: 4px;
  background: var(--el-border-color-lighter);
  cursor: col-resize;
  flex-shrink: 0;
  position: relative;
  transition: background-color 0.2s;
}

.resize-handle:hover {
  background: var(--el-color-primary);
}

.resize-handle:active {
  background: var(--el-color-primary);
}

.editor-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--el-bg-color);
  overflow: hidden;
  min-width: 400px;
}

.property-section {
  width: 350px;
  display: flex;
  flex-direction: column;
  background: var(--el-bg-color);
  overflow: hidden;
}

.notebook-section {
  display: flex;
  flex-direction: column;
  background: var(--el-bg-color);
  overflow: hidden;
  flex-shrink: 0;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: var(--el-fill-color-light);
  border-bottom: 1px solid var(--el-border-color);
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.section-subtitle {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

/* 校验结果样式 */
.validation-item {
  padding: 12px;
  margin-bottom: 8px;
  border-radius: 4px;
  border-left: 3px solid;
}

.error-item {
  background-color: var(--el-color-danger-light-9);
  border-left-color: var(--el-color-danger);
}

.warning-item {
  background-color: var(--el-color-warning-light-9);
  border-left-color: var(--el-color-warning);
}

.validation-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.validation-location {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.validation-variable {
  font-size: 12px;
  font-family: 'Courier New', monospace;
  color: var(--el-text-color-regular);
  background-color: var(--el-fill-color);
  padding: 2px 6px;
  border-radius: 3px;
}

.validation-message {
  font-size: 14px;
  color: var(--el-text-color-primary);
  margin-bottom: 4px;
}

.validation-suggestion {
  font-size: 13px;
  color: var(--el-text-color-regular);
  font-style: italic;
}
</style>
