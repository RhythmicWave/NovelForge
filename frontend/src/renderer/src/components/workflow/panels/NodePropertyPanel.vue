<template>
  <div class="node-property-panel">
    <div v-if="!props.node" class="empty-state">
      <el-empty description="请选择一个节点" :image-size="80" />
    </div>

    <div v-else class="panel-content">
      <!-- 节点信息头部 -->
      <div class="node-header">
        <div class="node-title">
          <el-tag type="primary" size="small">{{ props.node.category }}</el-tag>
          <span class="node-label">{{ nodeMetadata?.label || props.node.nodeType }}</span>
        </div>
        <p class="node-description">{{ nodeMetadata?.description }}</p>
      </div>

      <!-- 加载状态 -->
      <div v-if="loading" class="loading-state">
        <el-skeleton :rows="5" animated />
      </div>

      <!-- 配置表单 -->
      <el-form v-else-if="nodeMetadata" label-position="top" class="node-form">
        <el-form-item
          v-for="(field, fieldName) in formFields"
          :key="fieldName"
          :label="field.description || fieldName"
          :required="field.required"
        >
          <!-- 字符串输入 -->
          <el-input
            v-if="field.type === 'string' && !field.enum"
            v-model="formData[fieldName]"
            :placeholder="field.default || field.examples?.[0]"
            clearable
          />

          <!-- 数字输入 -->
          <el-input-number
            v-else-if="field.type === 'integer' || field.type === 'number'"
            v-model="formData[fieldName]"
            :min="field.minimum"
            :max="field.maximum"
            :placeholder="field.default"
            style="width: 100%"
          />

          <!-- 布尔值 -->
          <el-switch
            v-else-if="field.type === 'boolean'"
            v-model="formData[fieldName]"
          />

          <!-- 枚举选择 -->
          <el-select
            v-else-if="field.enum"
            v-model="formData[fieldName]"
            :placeholder="`请选择${field.description || fieldName}`"
            clearable
            style="width: 100%"
          >
            <el-option
              v-for="option in field.enum"
              :key="option"
              :label="option"
              :value="option"
            />
          </el-select>

          <!-- 项目选择器 -->
          <el-select
            v-else-if="fieldName === 'project_id'"
            v-model="formData[fieldName]"
            placeholder="请选择项目"
            filterable
            clearable
            style="width: 100%"
          >
            <el-option
              v-for="project in projects"
              :key="project.id"
              :label="project.name"
              :value="project.id"
            />
          </el-select>

          <!-- LLM配置选择器 -->
          <el-select
            v-else-if="fieldName === 'llm_config_id'"
            v-model="formData[fieldName]"
            placeholder="请选择LLM配置"
            filterable
            clearable
            style="width: 100%"
          >
            <el-option
              v-for="config in llmConfigs"
              :key="config.id"
              :label="config.display_name || config.model_name"
              :value="config.id"
            />
          </el-select>

          <!-- 提示词选择器 -->
          <el-select
            v-else-if="fieldName === 'prompt_id'"
            v-model="formData[fieldName]"
            placeholder="请选择提示词"
            filterable
            clearable
            style="width: 100%"
          >
            <el-option
              v-for="prompt in prompts"
              :key="prompt.id"
              :label="prompt.name"
              :value="prompt.id"
            />
          </el-select>

          <!-- 卡片类型选择器 -->
          <el-select
            v-else-if="fieldName === 'card_type' || fieldName === 'card_type_id'"
            v-model="formData[fieldName]"
            placeholder="请选择卡片类型"
            filterable
            clearable
            style="width: 100%"
          >
            <el-option
              v-for="cardType in cardTypes"
              :key="cardType.id"
              :label="cardType.name"
              :value="fieldName === 'card_type' ? cardType.name : cardType.id"
            />
          </el-select>

          <!-- 默认文本输入 -->
          <el-input
            v-else
            v-model="formData[fieldName]"
            :placeholder="field.default || field.examples?.[0]"
            clearable
          />
        </el-form-item>

        <!-- 应用按钮 -->
        <div class="form-actions">
          <el-button type="primary" @click="applyToCode" :icon="Check">
            更新节点
          </el-button>
          <el-button @click="resetForm" :icon="RefreshLeft">
            重置
          </el-button>
        </div>
      </el-form>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { Check, RefreshLeft } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { storeToRefs } from 'pinia'
import request from '@/api/request'
import { useProjectListStore } from '@/stores/useProjectListStore'
import { useCardStore } from '@/stores/useCardStore'
import { useLLMConfigStore } from '@/stores/useLLMConfigStore'
import { usePromptStore } from '@/stores/usePromptStore'

const props = defineProps({
  node: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['update'])

// 使用 store
const projectListStore = useProjectListStore()
const cardStore = useCardStore()
const llmConfigStore = useLLMConfigStore()
const promptStore = usePromptStore()

const { projects } = storeToRefs(projectListStore)
const { cardTypes } = storeToRefs(cardStore)
const { llmConfigs } = storeToRefs(llmConfigStore)
const { prompts } = storeToRefs(promptStore)

// 状态
const loading = ref(false)
const nodeMetadata = ref(null)
const formData = ref({})

// 计算表单字段
const formFields = computed(() => {
  if (!nodeMetadata.value?.input_schema?.properties) return {}
  return nodeMetadata.value.input_schema.properties
})

// 获取节点元数据
async function fetchNodeMetadata(nodeType) {
  loading.value = true
  try {
    const response = await request.get(`/nodes/${nodeType}/metadata`, undefined, '/api', {
      showLoading: false
    })
    nodeMetadata.value = response

    // 初始化表单数据
    initFormData()
  } catch (error) {
    console.error('获取节点元数据失败:', error)
    ElMessage.error('获取节点元数据失败')
  } finally {
    loading.value = false
  }
}

// 初始化表单数据
function initFormData() {
  const newFormData = {}
  const schema = nodeMetadata.value?.input_schema

  if (schema?.properties) {
    Object.entries(schema.properties).forEach(([key, field]) => {
      // 从当前节点参数中获取值，或使用默认值
      if (props.node?.params && props.node.params[key] !== undefined) {
        newFormData[key] = props.node.params[key]
      } else if (field.default !== undefined) {
        newFormData[key] = field.default
      } else {
        newFormData[key] = ''
      }
    })
  }

  formData.value = newFormData
}

// 重置表单
function resetForm() {
  initFormData()
  ElMessage.success('已重置表单')
}

// 应用到代码
function applyToCode() {
  if (!props.node) return

  // 生成参数字符串
  const params = []
  Object.entries(formData.value).forEach(([key, value]) => {
    if (value !== '' && value !== null && value !== undefined) {
      // 字符串类型加引号
      if (typeof value === 'string') {
        params.push(`${key}="${value}"`)
      } else {
        params.push(`${key}=${value}`)
      }
    }
  })

  // 生成新的代码行
  const newCode = `${props.node.variable} = ${props.node.nodeType}(${params.join(', ')})`

  // 更新节点
  emit('update', { ...props.node, code: newCode, params: formData.value })
  ElMessage.success('已更新节点')
}

// 加载所有选择器数据
async function loadSelectorData() {
  try {
    // 确保数据已加载
    if (projects.value.length === 0) {
      await projectListStore.fetchProjects()
    }

    if (cardTypes.value.length === 0) {
      await cardStore.fetchCardTypes()
    }

    if (llmConfigs.value.length === 0) {
      await llmConfigStore.fetchLLMConfigs()
    }

    if (prompts.value.length === 0) {
      await promptStore.fetchPrompts()
    }
  } catch (error) {
    console.error('加载选择器数据失败:', error)
  }
}

// 监听节点变化
watch(() => props.node, (newNode) => {
  if (newNode) {
    fetchNodeMetadata(newNode.nodeType)
  } else {
    nodeMetadata.value = null
  }
}, { immediate: true })

// 组件挂载时加载数据
onMounted(() => {
  loadSelectorData()
})
</script>

<style scoped>
.node-property-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: white;
  border-left: 1px solid #ebeef5;
}

.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.panel-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.node-header {
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid #ebeef5;
}

.node-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.node-label {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.node-description {
  margin: 0;
  font-size: 13px;
  color: #606266;
  line-height: 1.5;
}

.loading-state {
  padding: 20px 0;
}

.node-form {
  margin-top: 16px;
}

.form-actions {
  display: flex;
  gap: 8px;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid #ebeef5;
}

.form-actions .el-button {
  flex: 1;
}
</style>
