
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
        <el-select v-model="selectedTemplateId" placeholder="选择项目模板" filterable clearable :loading="loadingTemplates">
          <el-option v-for="tpl in templates" :key="tpl.id" :label="tpl.name" :value="tpl.id" />
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
import { listProjectTemplates, type ProjectTemplate } from '@renderer/api/setting'

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

const selectedTemplateId = ref<number | null>(null)
const templates = ref<ProjectTemplate[]>([])
const loadingTemplates = ref(false)

const isEditMode = computed(() => !!editingProject.value)
const dialogTitle = computed(() => isEditMode.value ? '编辑项目' : '新建项目')

const rules = reactive<FormRules>({
  name: [{ required: true, message: '请输入项目名称', trigger: 'blur' }]
})

const emit = defineEmits(['create', 'update'])

async function loadTemplates() {
  try {
    loadingTemplates.value = true
    templates.value = await listProjectTemplates()
    // 默认选中第一个内置模板（若存在）
    const builtInFirst = templates.value.find(t => t.built_in)
    selectedTemplateId.value = builtInFirst?.id ?? templates.value[0]?.id ?? null
  } catch (e) {
    // 忽略错误，允许无模板情况下创建
    selectedTemplateId.value = null
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
      // 编辑模式下不显示模板字段
      selectedTemplateId.value = null
    } else {
      form.name = ''
      form.description = ''
      // 重载模板（保证最新）
      loadTemplates()
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
        if (selectedTemplateId.value) payload.template_id = selectedTemplateId.value
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