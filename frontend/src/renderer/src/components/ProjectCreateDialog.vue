
<template>
  <el-dialog v-model="visible" :title="dialogTitle" width="500" >
    <el-form :model="form" ref="formRef" :rules="rules" label-width="80px" @submit.prevent="handleConfirm">
      <el-form-item label="项目名称" prop="name">
        <el-input v-model="form.name" />
      </el-form-item>
      <el-form-item label="项目描述" prop="description">
        <el-input v-model="form.description" type="textarea" />
      </el-form-item>
      <el-form-item v-if="!isEditMode" label="项目模板">
        <el-select v-model="selectedWorkflowId" placeholder="选择初始化工作流(类型:onprojectcreate)" filterable clearable :loading="loadingWorkflows" style="width:100%">
          <el-option v-for="wf in initWorkflows" :key="wf.id" :label="wf.name" :value="wf.id" />
        </el-select>
      </el-form-item>
      <!-- 隐藏的提交按钮，确保在输入框按回车会触发表单提交 -->
      <button type="submit" style="display:none"></button>
    </el-form>
    <template #footer>
      <div class="dialog-footer">
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" @click="handleConfirm">确定</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, computed, nextTick, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import type { components } from '@renderer/types/generated'
import { listWorkflows, type WorkflowRead } from '@renderer/api/workflows'

type Project = components['schemas']['ProjectRead']
type ProjectCreate = components['schemas']['ProjectCreate']
type ProjectUpdate = components['schemas']['ProjectUpdate']


const visible = ref(false)
const formRef = ref<FormInstance>()
const form = reactive<ProjectCreate | ProjectUpdate>({
  name: '',
  description: ''
})
const editingProject = ref<Project | null>(null)

// 工作流模式
const selectedWorkflowId = ref<number | null>(null)
const initWorkflows = ref<WorkflowRead[]>([])
const loadingWorkflows = ref(false)

const isEditMode = computed(() => !!editingProject.value)
const dialogTitle = computed(() => isEditMode.value ? '编辑项目' : '新建项目')

const rules = reactive<FormRules>({
  name: [{ required: true, message: '请输入项目名称', trigger: 'blur' }]
})

const emit = defineEmits(['create', 'update'])


async function loadInitWorkflows() {
  try {
    loadingWorkflows.value = true
    const all = await listWorkflows()
    // Filter workflows that have a 'Trigger.ProjectCreated' node
    initWorkflows.value = all.filter(w => {
      const nodes = (w.definition_json?.nodes || []) as any[]
      return Array.isArray(nodes) && nodes.some((n: any) => n.type === 'Trigger.ProjectCreated')
    })
    
    if (initWorkflows.value.length) {
      selectedWorkflowId.value = initWorkflows.value[0]?.id ?? null
    } else {
      selectedWorkflowId.value = null
    }
  } finally {
    loadingWorkflows.value = false
  }
}

function open(project: Project | null = null) {
  visible.value = true
  editingProject.value = project
  
  nextTick(() => {
    formRef.value?.resetFields()
    if (project) {
      form.name = project.name
      form.description = project.description || ''
    } else {
      form.name = ''
      form.description = ''
      // 重载工作流（保证最新）
      loadInitWorkflows()
    }
  })
}

function handleConfirm() {
  formRef.value?.validate((valid) => {
    if (valid) {
      if (isEditMode.value && editingProject.value) {
        emit('update', editingProject.value.id, { ...form })
      } else {
        const payload: any = { ...form }
        if (selectedWorkflowId.value) payload.workflow_id = selectedWorkflowId.value
        emit('create', payload)
      }
      visible.value = false
    } else {
      ElMessage.error('请填写必要的表单项')
    }
  })
}

// 暴露 open 方法给父组件
defineExpose({
  open
})
// 样式
</script>

<style scoped>
.mode-switch { margin-bottom: 8px; }
.selector-block { width: 100%; }
</style>