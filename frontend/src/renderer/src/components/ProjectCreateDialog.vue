
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
        <el-select v-model="selectedTemplate" placeholder="选择项目模板（可选）" filterable clearable :loading="loadingTemplates" style="width:100%">
          <el-option label="空白项目" :value="null" />
          <el-option v-for="tpl in projectTemplates" :key="tpl.template" :label="tpl.workflow_name" :value="tpl.template" />
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
import { ref, reactive, computed, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import type { components } from '@renderer/types/generated'
import { getProjectTemplates } from '@renderer/api/workflows'

type Project = components['schemas']['ProjectRead']
type ProjectCreate = components['schemas']['ProjectCreate']
type ProjectUpdate = components['schemas']['ProjectUpdate']

interface ProjectTemplate {
  workflow_id: number
  workflow_name: string
  template: string | null
  description?: string
}

const visible = ref(false)
const formRef = ref<FormInstance>()
const form = reactive<ProjectCreate | ProjectUpdate>({
  name: '',
  description: ''
})
const editingProject = ref<Project | null>(null)

// 项目模板
const selectedTemplate = ref<string | null>(null)
const projectTemplates = ref<ProjectTemplate[]>([])
const loadingTemplates = ref(false)

const isEditMode = computed(() => !!editingProject.value)
const dialogTitle = computed(() => isEditMode.value ? '编辑项目' : '新建项目')

const rules = reactive<FormRules>({
  name: [{ required: true, message: '请输入项目名称', trigger: 'blur' }]
})

const emit = defineEmits(['create', 'update'])

async function loadProjectTemplates() {
  try {
    loadingTemplates.value = true
    const response = await getProjectTemplates()
    projectTemplates.value = response.templates || []
    
    // 默认选择第一个模板（如果有）
    if (projectTemplates.value.length > 0) {
      selectedTemplate.value = projectTemplates.value[0].template
    }
  } catch (error) {
    console.error('加载项目模板失败:', error)
    ElMessage.error('加载项目模板失败')
  } finally {
    loadingTemplates.value = false
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
      selectedTemplate.value = null
      // 加载项目模板
      loadProjectTemplates()
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
        // 显式传递 template 参数（null 表示空白项目）
        payload.template = selectedTemplate.value
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
</script>

<style scoped>
.mode-switch { margin-bottom: 8px; }
.selector-block { width: 100%; }
</style>