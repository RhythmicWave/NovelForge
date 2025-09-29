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
      <el-table-column prop="api_base" label="API Base" width="240" />
      <el-table-column prop="token_limit" label="Token上限" width="90" />
      <el-table-column prop="call_limit" label="调用上限" width="90" />
      <el-table-column width="200">
        <template #header>
          <span>
            已用（输入/输出/调用）
            <el-tooltip placement="top" effect="dark">
              <template #content>
                token 估算规则：<br/>
                - 中文每个汉字计 1<br/>
                - 英文单词计 1<br/>
                - 每个数字计 1<br/>
                - 非空白符号各计 1<br/>
                注意：不同模型 token 计算不同，此为粗略估算，仅供参考。<br/>
                <br/>
                显示格式：<br/>
                - ≥1万：显示为 X.XXX 万<br/>
                - ≥1百万：显示为 X.XXX 百万<br/>
                - 最多保留3位小数，自动去除末尾0
              </template>
              <el-icon style="margin-left:4px; cursor: help;"><QuestionFilled /></el-icon>
            </el-tooltip>
          </span>
        </template>
        <template #default="{ row }">
          {{ formatNumber((row as any).used_tokens_input || 0) }} / {{ formatNumber((row as any).used_tokens_output || 0) }} / {{ formatNumber((row as any).used_calls || 0) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="200">
        <template #default="{ row }">
          <el-button size="small" @click="openEditDialog(row)">编辑</el-button>
          <el-button size="small" type="danger" @click="deleteConfig(row.id)">删除</el-button>
          <el-button size="small" type="warning" @click="handleReset(row)" plain>重置</el-button>
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
import { QuestionFilled } from '@element-plus/icons-vue'
import LLMConfigForm from './LLMConfigForm.vue'
import type { components } from '@renderer/types/generated'
import { listLLMConfigs, createLLMConfig, updateLLMConfig, deleteLLMConfig, resetLLMUsage } from '@renderer/api/setting'

type LLMConfig = components['schemas']['LLMConfigRead']

const llmConfigs = ref<LLMConfig[]>([])
const editDialogVisible = ref(false)
const editConfig = ref<LLMConfig | null>(null)

/**
 * 格式化数字显示
 * @param num 数字
 * @returns 格式化后的字符串
 */
function formatNumber(num: number): string {
  if (num >= 1000000) {
    // 大于等于1百万，显示为 X.XXX 百万
    const millions = num / 1000000
    const formatted = millions.toFixed(3)
    // 去除末尾的0
    const trimmed = parseFloat(formatted).toString()
    return `${trimmed} 百万`
  } else if (num >= 10000) {
    // 大于等于1万，显示为 X.XXX 万
    const tenThousands = num / 10000
    const formatted = tenThousands.toFixed(3)
    // 去除末尾的0
    const trimmed = parseFloat(formatted).toString()
    return `${trimmed} 万`
  } else {
    // 小于1万，直接显示原数字
    return num.toString()
  }
}

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

async function handleReset(row: LLMConfig) {
  try {
    await ElMessageBox.confirm('确认将该配置的统计（输入/输出token、调用次数）清零？', '重置统计', {
      type: 'warning', confirmButtonText: '确定', cancelButtonText: '取消'
    })
  } catch (e) {
    return
  }
  try {
    await resetLLMUsage(row.id)
    ElMessage.success('已重置')
    await loadLLMConfigs()
  } catch (e) {
    ElMessage.error('重置失败')
  }
}

// 暴露 refresh 给父组件调用
defineExpose({ refresh: loadLLMConfigs })
onMounted(loadLLMConfigs)
</script>

<style scoped>
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
</style> 