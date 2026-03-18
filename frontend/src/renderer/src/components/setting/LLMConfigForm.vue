<template>
  <el-form :model="form" ref="formRef" :rules="rules" label-width="140px" autocomplete="off">
    <div style="height: 0; overflow: hidden; position: absolute; opacity: 0;">
      <input type="text" autocomplete="username" tabindex="-1">
      <input type="password" autocomplete="new-password" tabindex="-1">
    </div>

    <el-form-item label="提供商" prop="provider">
      <el-select v-model="form.provider" placeholder="请选择提供商">
        <el-option label="OpenAI兼容" value="openai_compatible" />
        <el-option label="OpenAI" value="openai" />
        <el-option label="Google" value="google" />
        <el-option label="Anthropic" value="anthropic" />
      </el-select>
    </el-form-item>

    <el-form-item label="显示名称" prop="display_name">
      <el-input v-model="form.display_name" placeholder="可选，留空时自动设置为模型名称" />
    </el-form-item>

    <el-form-item label="API Base" prop="api_base">
      <el-input
        v-model="form.api_base"
        :disabled="!isOpenAIProvider"
        :input-props="{ autocomplete: 'off', name: 'api_base_no_fill' }"
        placeholder="例如: https://api.openai.com/v1 或 https://api.siliconflow.cn/v1"
      />
    </el-form-item>

    <el-form-item label="API Key" prop="api_key">
      <el-input
        v-model="form.api_key"
        type="password"
        :input-props="{ autocomplete: 'new-password', name: 'api_key_no_fill' }"
        placeholder="API密钥将直接保存在后端"
        show-password
      />
    </el-form-item>

    <el-form-item label="模型名称" prop="model_name">
      <div style="display: flex; width: 100%; gap: 10px; align-items: center;">
        <el-autocomplete
          v-model="form.model_name"
          :fetch-suggestions="querySearch"
          placeholder="输入或选择模型名称"
          style="flex: 1; width: 100%;"
          clearable
        />
        <el-button
          :loading="loadingModels"
          :icon="Refresh"
          title="获取模型列表"
          @click="handleFetchModels"
        >
          获取
        </el-button>
      </div>
    </el-form-item>

    <el-form-item v-if="isOpenAIProvider" label="协议与兼容">
      <div class="transport-settings">
        <div class="transport-summary">
          <div class="transport-copy">
            <div class="transport-title">多数平台只需 API Base</div>
            <div class="transport-desc">非标准网关再展开兼容设置。</div>
          </div>
          <el-button text type="primary" @click="showAdvancedTransport = !showAdvancedTransport">
            {{ showAdvancedTransport ? '收起设置' : '兼容设置' }}
          </el-button>
        </div>

        <div v-if="showAdvancedTransport" class="transport-panel">
          <el-form-item label="协议模式" label-width="96px" class="inline-item">
            <el-select v-model="form.api_protocol">
              <el-option label="Chat 模式" value="chat_completions" />
              <el-option label="Responses 模式" value="responses" />
            </el-select>
          </el-form-item>

          <div class="transport-rare-toggle">
            <span class="rare-toggle-text">以下字段仅少数兼容网关需要。</span>
            <el-button text @click="showRareTransportFields = !showRareTransportFields">
              {{ showRareTransportFields ? '隐藏字段' : '更多字段' }}
            </el-button>
          </div>

          <div v-if="showRareTransportFields" class="rare-transport-grid">
            <el-form-item label="自定义请求路径" label-width="96px" class="inline-item">
              <el-input
                v-model="form.custom_request_path"
                placeholder="可选，如 /v1/gateway"
                :disabled="!isOpenAIProvider"
              />
            </el-form-item>

            <el-form-item label="模型列表路径" label-width="96px" class="inline-item">
              <el-input
                v-model="form.models_path"
                placeholder="可选，默认 /models"
                :disabled="!isOpenAIProvider"
              />
            </el-form-item>

            <el-form-item label="User-Agent" label-width="96px" class="inline-item">
              <el-input
                v-model="form.user_agent"
                placeholder="可选，自定义请求头 User-Agent"
                :disabled="!isOpenAIProvider"
              />
            </el-form-item>
          </div>
        </div>
      </div>
    </el-form-item>

    <el-form-item label="Token上限" prop="token_limit">
      <el-input-number v-model="form.token_limit" :min="-1" :step="1000" />
      <span style="margin-left: 8px; color: #888">-1 表示不限</span>
    </el-form-item>

    <el-form-item label="调用次数上限" prop="call_limit">
      <el-input-number v-model="form.call_limit" :min="-1" />
      <span style="margin-left: 8px; color: #888">-1 表示不限</span>
    </el-form-item>

    <el-form-item>
      <el-button @click="handleCancel">取消</el-button>
      <el-button type="primary" @click="handleSubmit">保存</el-button>
      <el-button @click="handleTest">测试连接</el-button>
    </el-form-item>
  </el-form>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import type { components } from '@renderer/types/generated'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'

import { getLLMModels, testLLMConnection } from '@renderer/api/setting'

type LLMConfig = components['schemas']['LLMConfigRead']
type LLMApiProtocol = 'chat_completions' | 'responses'

const props = defineProps<{
  initialData?: LLMConfig | null
}>()

const emit = defineEmits(['save', 'cancel'])
const formRef = ref<FormInstance>()

const fetchedModels = ref<string[]>([])
const loadingModels = ref(false)
const showAdvancedTransport = ref(false)
const showRareTransportFields = ref(false)

const form = reactive({
  id: null as number | null,
  provider: 'openai_compatible',
  display_name: '',
  model_name: '',
  api_base: '',
  api_key: '',
  api_protocol: 'chat_completions' as LLMApiProtocol,
  custom_request_path: '',
  models_path: '',
  user_agent: '',
  token_limit: -1,
  call_limit: -1,
})

const isOpenAIProvider = computed(() => form.provider === 'openai' || form.provider === 'openai_compatible')

const querySearch = (queryString: string, cb: any) => {
  const results = queryString
    ? fetchedModels.value.filter((item) => item.toLowerCase().includes(queryString.toLowerCase()))
    : fetchedModels.value
  cb(results.map((value) => ({ value })))
}

const rules = reactive<FormRules>({
  provider: [{ required: true, message: '请选择提供商', trigger: 'change' }],
  model_name: [{ required: true, message: '请输入模型名称', trigger: 'blur' }],
  api_key: [{ required: true, message: '请输入API Key', trigger: 'blur' }],
  token_limit: [{ required: true, message: '请输入Token上限', trigger: 'blur' }],
  call_limit: [{ required: true, message: '请输入调用次数上限', trigger: 'blur' }],
})

watch(
  () => form.provider,
  (provider) => {
    if (!['openai', 'openai_compatible'].includes(provider)) {
      form.api_protocol = 'chat_completions'
      form.custom_request_path = ''
      form.models_path = ''
      form.user_agent = ''
      showAdvancedTransport.value = false
      showRareTransportFields.value = false
    }
  },
)

watch(
  () => props.initialData,
  (newData) => {
    if (newData) {
      form.id = newData.id
      form.provider = newData.provider
      form.display_name = newData.display_name || ''
      form.model_name = newData.model_name
      form.api_base = newData.api_base || ''
      form.api_key = newData.api_key || ''
      form.api_protocol = (((newData as any).api_protocol || 'chat_completions') === 'responses' ? 'responses' : 'chat_completions') as LLMApiProtocol
      form.custom_request_path = (newData as any).custom_request_path || ''
      form.models_path = (newData as any).models_path || ''
      form.user_agent = (newData as any).user_agent || ''
      form.token_limit = (newData as any).token_limit ?? -1
      form.call_limit = (newData as any).call_limit ?? -1
      showAdvancedTransport.value = form.api_protocol !== 'chat_completions' || !!form.custom_request_path || !!form.models_path || !!form.user_agent
      showRareTransportFields.value = !!form.custom_request_path || !!form.models_path || !!form.user_agent
      return
    }

    form.id = null
    form.provider = 'openai_compatible'
    form.display_name = ''
    form.model_name = ''
    form.api_base = ''
    form.api_key = ''
    form.api_protocol = 'chat_completions'
    form.custom_request_path = ''
    form.models_path = ''
    form.user_agent = ''
    form.token_limit = -1
    form.call_limit = -1
    showAdvancedTransport.value = false
    showRareTransportFields.value = false
  },
  { immediate: true },
)

function buildTransportPayload() {
  return {
    api_protocol: form.api_protocol || 'chat_completions',
    custom_request_path: form.custom_request_path.trim() || undefined,
    models_path: form.models_path.trim() || undefined,
    user_agent: form.user_agent.trim() || undefined,
  }
}

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) {
    ElMessage.warning('请检查输入项是否填写正确')
    return
  }

  emit('save', {
    ...form,
    ...buildTransportPayload(),
    api_base: form.api_base.trim() || undefined,
  })
}

async function handleFetchModels() {
  if (!form.api_key) {
    ElMessage.warning('请先输入API Key')
    return
  }

  loadingModels.value = true
  fetchedModels.value = []
  try {
    const models = await getLLMModels({
      provider: form.provider,
      api_base: form.api_base.trim() || undefined,
      api_key: form.api_key,
      ...buildTransportPayload(),
    } as any)
    fetchedModels.value = models
    if (models.length > 0) {
      ElMessage.success(`成功获取 ${models.length} 个模型`)
    } else {
      ElMessage.info('未获取到模型列表')
    }
  } catch (e: any) {
    ElMessage.error(`获取模型列表失败: ${e?.message || e}`)
  } finally {
    loadingModels.value = false
  }
}

function handleCancel() {
  emit('cancel')
}

async function handleTest() {
  try {
    await testLLMConnection({
      provider: form.provider,
      model_name: form.model_name,
      api_base: form.api_base.trim() || undefined,
      api_key: form.api_key,
      ...buildTransportPayload(),
    } as any)
    ElMessage.success('连接成功')
  } catch (e: any) {
    ElMessage.error(`连接失败：${e?.message || e}`)
  }
}
</script>

<style scoped>
.transport-settings {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
}

.transport-summary {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  background: var(--el-fill-color-extra-light);
}

.transport-copy {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.transport-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  line-height: 1.4;
}

.transport-desc {
  font-size: 12px;
  line-height: 1.5;
  color: var(--el-text-color-secondary);
}

.transport-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  background: var(--el-bg-color-page);
}

.transport-rare-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 2px 0 0;
}

.rare-toggle-text {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.rare-transport-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 8px;
}

.inline-item {
  margin-bottom: 0;
}

.inline-item :deep(.el-form-item__content) {
  min-width: 0;
}

.inline-item :deep(.el-select),
.inline-item :deep(.el-input) {
  width: 100%;
}
</style>
