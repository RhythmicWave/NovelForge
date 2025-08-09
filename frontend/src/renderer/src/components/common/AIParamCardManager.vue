<template>
  <div class="ai-param-card-manager">
    <div class="header">
      <h4>AI参数卡片管理</h4>
      <el-button type="primary" size="small" @click="openEditDialog()">新建卡片</el-button>
    </div>
    <el-table :data="aiParamCardStore.paramCards" style="width: 100%" size="small">
      <el-table-column prop="name" label="卡片名称" width="160" />
      <el-table-column prop="description" label="描述" min-width="160" />
      <el-table-column label="模型" width="140">
        <template #default="{ row }">
          {{ getLLMConfigName(row.llm_config_id) }}
        </template>
      </el-table-column>
      <el-table-column label="提示词" width="160">
        <template #default="{ row }">
          {{ row.prompt_name || '未选择' }}
        </template>
      </el-table-column>
      <el-table-column label="输出模型" width="200">
        <template #default="{ row }">
          {{ row.response_model_name || '自动选择' }}
        </template>
      </el-table-column>
      <el-table-column prop="temperature" label="温度" width="80" />
      <el-table-column prop="max_tokens" label="最大Token" width="100" />
      <el-table-column label="操作" width="180">
        <template #default="{ row, $index }">
          <el-button size="small" @click="openEditDialog(row, $index)">编辑</el-button>
          <el-button size="small" type="danger" @click="deleteCard($index)" :disabled="isBuiltInParamCard(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-dialog v-model="editDialogVisible" title="编辑AI参数卡片" width="520px">
      <el-form :model="editCard" label-width="90px">
        <el-form-item label="卡片名称">
          <el-input v-model="editCard.name" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="editCard.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="模型">
          <el-select v-model="editCard.llm_config_id" placeholder="选择模型" style="width: 100%">
            <el-option
              v-for="config in llmConfigs"
              :key="config.id"
              :label="config.display_name"
              :value="config.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="提示词">
          <el-select v-model="editCard.prompt_name" placeholder="选择提示词" style="width: 100%">
            <el-option
              v-for="prompt in prompts"
              :key="prompt.id"
              :label="prompt.name"
              :value="prompt.name"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="输出模型">
          <el-select v-model="editCard.response_model_name" placeholder="选择输出模型" style="width: 100%">
            <el-option label="自动选择" value="" />
            <el-option
              v-for="model in responseModels"
              :key="model"
              :label="model"
              :value="model"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="温度">
          <el-input-number v-model="editCard.temperature" :min="0" :max="2" :step="0.1" style="width: 100%" />
        </el-form-item>
        <el-form-item label="最大Token">
          <el-input-number v-model="editCard.max_tokens" :min="100" :max="4000" :step="100" style="width: 100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveCard">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getAIConfigOptions } from '@renderer/api/ai'
import { useAIParamCardStore, AIParamCard } from '../../stores/useAIParamCardStore'

const aiParamCardStore = useAIParamCardStore()

const editDialogVisible = ref(false)
const editCard = reactive<AIParamCard>({
  name: '',
  id: '',
  prompt_name: ''
})
let editIndex = -1

// 从后端获取的配置数据
const llmConfigs = ref<Array<{ id: number; display_name: string }>>([])
const prompts = ref<Array<{ id: number; name: string; description: string | null }>>([])
const responseModels = ref<string[]>([])

// 预设 AI 参数卡片名称（禁删）
const PRESET_PARAM_CARD_NAMES = new Set([
  '金手指生成','一句话梗概生成','大纲扩写生成','世界观生成','蓝图生成','分卷大纲生成','章节大纲生成'
])
const isBuiltInParamCard = (row: AIParamCard) => PRESET_PARAM_CARD_NAMES.has(row.name)

// 加载配置数据
async function loadConfigData() {
  try {
    const config = await getAIConfigOptions()
    llmConfigs.value = config.llm_configs
    prompts.value = config.prompts
    responseModels.value = config.response_models
  } catch (error) {
    console.error('Failed to load AI config options:', error)
  }
}

function getLLMConfigName(id: number | undefined): string {
  if (!id) return '未选择'
  const config = llmConfigs.value.find(c => c.id === id)
  return config ? config.display_name : '未知模型'
}

onMounted(() => {
  loadConfigData()
  aiParamCardStore.loadFromLocal()
})

async function openEditDialog(card?: AIParamCard, index?: number) {
  await loadConfigData()
  if (card) {
    Object.assign(editCard, card)
    editIndex = index ?? -1
  } else {
    Object.assign(editCard, {
      id: `card-${Date.now()}`,
      name: '',
      description: '',
      llm_config_id: undefined,
      prompt_name: '',
      response_model_name: '',
      temperature: 0.7,
      max_tokens: 2000
    })
    editIndex = -1
  }
  editDialogVisible.value = true
}

function saveCard() {
  if (!editCard.name) {
    ElMessage.warning('卡片名称不能为空')
    return
  }
  
  if (editIndex >= 0) {
    aiParamCardStore.updateCard(editIndex, { ...editCard })
  } else {
    aiParamCardStore.addCard({ ...editCard })
  }
  editDialogVisible.value = false
  ElMessage.success('保存成功')
}

function deleteCard(index: number) {
  aiParamCardStore.deleteCard(index)
  ElMessage.success('已删除')
}
</script>

<style scoped>
.ai-param-card-manager { padding: 16px; }
.header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
</style> 