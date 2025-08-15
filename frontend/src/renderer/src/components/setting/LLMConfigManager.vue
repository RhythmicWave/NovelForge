<template>
  <div class="llm-config-manager">
    <div class="header">
      <h4>LLM配置管理</h4>
      <el-button type="primary" size="small" @click="openEditDialog()">新增配置</el-button>
    </div>
    
    <el-table :data="llmConfigs" style="width: 100%" size="small">
      <el-table-column prop="display_name" label="显示名称" width="150" />
      <el-table-column prop="provider" label="提供商" width="120" />
      <el-table-column prop="model_name" label="模型名称" width="200" />
      <el-table-column prop="api_base" label="API Base" width="250" />
      <el-table-column label="操作" width="200">
        <template #default="{ row }">
          <el-button size="small" @click="openEditDialog(row)">编辑</el-button>
          <el-button size="small" type="danger" @click="deleteConfig(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 编辑对话框 -->
    <el-dialog v-model="editDialogVisible" title="编辑LLM配置" width="500px">
      <LLMConfigForm 
        :initial-data="editConfig" 
        @save="handleSave"
        @cancel="editDialogVisible = false"
      />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import LLMConfigForm from './LLMConfigForm.vue'
import type { components } from '@renderer/types/generated'
import { listLLMConfigs, createLLMConfig, updateLLMConfig, deleteLLMConfig } from '@renderer/api/setting'

type LLMConfig = components['schemas']['LLMConfigRead']

const llmConfigs = ref<LLMConfig[]>([])
const editDialogVisible = ref(false)
const editConfig = ref<LLMConfig | null>(null)

async function loadLLMConfigs() {
  try {
    llmConfigs.value = await listLLMConfigs()
  } catch (error) {
    console.error('Failed to load LLM configs:', error)
    ElMessage.error('加载LLM配置失败')
  }
}

function openEditDialog(config?: LLMConfig) {
  if (config) {
    // 编辑现有配置
    editConfig.value = config
  } else {
    // 新增配置
    editConfig.value = null
  }
  editDialogVisible.value = true
}

async function handleSave(data: any) {
  try {
    if (data.id) {
      await updateLLMConfig(data.id, data)
      ElMessage.success('LLM配置更新成功！')
    } else {
      await createLLMConfig(data)
      ElMessage.success('LLM配置创建成功！')
    }
    editDialogVisible.value = false
    await loadLLMConfigs() // 重新加载列表
  } catch (error) {
    ElMessage.error('保存失败，请检查输入信息')
  }
}

async function deleteConfig(id: number) {
  try {
    await ElMessageBox.confirm('确定要删除这个LLM配置吗？', '确认删除', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    await deleteLLMConfig(id)
    ElMessage.success('删除成功')
    await loadLLMConfigs() // 重新加载列表
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

onMounted(() => {
  loadLLMConfigs()
})
</script>

<style scoped>
.llm-config-manager {
  padding: 16px;
}
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
</style> 