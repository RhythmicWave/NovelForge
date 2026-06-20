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

    <el-form-item label="模型能力">
      <div class="capability-panel">
        <div class="capability-actions">
          <el-button :loading="capabilityLoading" @click="handleCapabilityTest(false)">完整能力检测</el-button>
          <el-button :loading="capabilityLoading" type="warning" plain @click="handleCapabilityTest(true)">尝试兼容修复</el-button>
          <el-button
            v-if="capabilityResult"
            type="primary"
            plain
            :disabled="!canApplyCapabilityRecommendation"
            @click="applyCapabilityRecommendation"
          >
            应用推荐配置
          </el-button>
        </div>

        <el-alert
          v-if="capabilityResult"
          :title="capabilityResult.summary"
          :type="overallAlertType"
          show-icon
          :closable="false"
        />

        <div v-if="capabilityResult" class="capability-tags">
          <el-tag v-for="tag in capabilityResult.tags" :key="tag" size="small" :type="tagType(tag)">
            {{ tag }}
          </el-tag>
        </div>

        <div v-if="capabilityResult" class="capability-grid">
          <div v-for="item in capabilityTestItems" :key="item.key" class="capability-item">
            <span class="capability-name">{{ item.label }}</span>
            <el-tag size="small" :type="statusTagType(item.result.status)">
              {{ statusText(item.result.status) }}
            </el-tag>
            <span class="capability-message">{{ item.result.message }}</span>
          </div>
        </div>

        <div v-if="capabilityResult" class="recommendation">
          <div>推荐用途：{{ overallText(capabilityResult.overall) }}</div>
          <div>推荐修复：{{ recommendationText }}</div>
        </div>
      </div>
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

import { getLLMModels, testLLMCapability, testLLMConnection } from '@renderer/api/setting'
import type { LLMCapabilityTestResult } from '@renderer/api/setting'

type LLMConfig = components['schemas']['LLMConfigRead']
type LLMApiProtocol = 'chat_completions' | 'responses'
type LLMAssistantMode = 'auto' | 'standard' | 'react' | 'plain'

const props = defineProps<{
  initialData?: LLMConfig | null
}>()

const emit = defineEmits(['save', 'cancel', 'refresh'])
const formRef = ref<FormInstance>()

const fetchedModels = ref<string[]>([])
const loadingModels = ref(false)
const capabilityLoading = ref(false)
const capabilityResult = ref<LLMCapabilityTestResult | null>(null)
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
  capability_summary: null as any,
  recommended_assistant_mode: 'auto' as LLMAssistantMode,
  disable_stream: false,
  capability_last_checked_at: null as string | null,
  token_limit: -1,
  call_limit: -1,
})

const isOpenAIProvider = computed(() => form.provider === 'openai' || form.provider === 'openai_compatible')
const overallAlertType = computed(() => {
  const overall = capabilityResult.value?.overall
  if (overall === 'full' || overall === 'react_assistant' || overall === 'writing_review_only') return 'success'
  if (overall === 'plain_only' || overall === 'unknown') return 'warning'
  return 'error'
})

const basicChatPassed = computed(() => capabilityResult.value?.tests?.basic_chat?.status === 'pass')
const canApplyCapabilityRecommendation = computed(() => !!capabilityResult.value && basicChatPassed.value)

const capabilityTestItems = computed(() => {
  const tests = capabilityResult.value?.tests
  if (!tests) return []
  return [
    { key: 'models_list', label: '模型列表', result: tests.models_list },
    { key: 'basic_chat', label: '基础连接', result: tests.basic_chat },
    { key: 'review', label: '普通审核', result: tests.review },
    { key: 'stream', label: '流式输出', result: tests.stream },
    { key: 'structured', label: '结构化输出', result: tests.structured },
    { key: 'native_tools', label: '原生工具调用', result: tests.native_tools },
    { key: 'react_tools', label: 'ReAct 工具模式', result: tests.react_tools },
  ]
})

const recommendationText = computed(() => {
  const mode = capabilityResult.value?.recommended_mode
  if (!mode) return '暂无'
  if (!basicChatPassed.value) return '需先修复基础连接'
  const parts: string[] = []
  if (mode.disable_stream) parts.push('关闭流式')
  if (mode.assistant_mode === 'react') parts.push('灵感助手使用 ReAct')
  if (mode.assistant_mode === 'plain') parts.push('仅普通对话/审核')
  if (mode.api_protocol !== form.api_protocol) parts.push(`切换协议为 ${mode.api_protocol}`)
  if (mode.use_default_user_agent && mode.recommended_user_agent) parts.push(`补 User-Agent: ${mode.recommended_user_agent}`)
  return parts.length ? parts.join('；') : '无需兼容修复'
})

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
      form.capability_summary = (newData as any).capability_summary || null
      form.recommended_assistant_mode = ((newData as any).recommended_assistant_mode || 'auto') as LLMAssistantMode
      form.disable_stream = !!(newData as any).disable_stream
      form.capability_last_checked_at = (newData as any).capability_last_checked_at || null
      capabilityResult.value = form.capability_summary as LLMCapabilityTestResult | null
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
    form.capability_summary = null
    form.recommended_assistant_mode = 'auto'
    form.disable_stream = false
    form.capability_last_checked_at = null
    capabilityResult.value = null
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
    capability_summary: form.capability_summary || undefined,
    recommended_assistant_mode: form.recommended_assistant_mode,
    disable_stream: form.disable_stream,
    capability_last_checked_at: form.capability_last_checked_at || undefined,
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

async function handleCapabilityTest(tryRepair: boolean) {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) {
    ElMessage.warning('请先填写必要的模型配置')
    return
  }

  capabilityLoading.value = true
  try {
    const result = await testLLMCapability({
      provider: form.provider,
      model_name: form.model_name,
      api_base: form.api_base.trim() || undefined,
      api_key: form.api_key,
      ...buildTransportPayload(),
      test_models_list: true,
      try_repair: tryRepair,
      save_result: tryRepair && !!form.id,
      config_id: form.id,
    } as any)
    capabilityResult.value = result
    const repairedWithUserAgent = !!result.recommended_mode.use_default_user_agent && !!result.recommended_mode.recommended_user_agent
    if (tryRepair && result.tests.basic_chat.status === 'pass' && repairedWithUserAgent) {
      applyCapabilityRecommendationToForm()
      if (form.id) {
        emit('refresh')
        ElMessage.success('兼容配置已保存')
      } else {
        ElMessage.success('已应用兼容配置，请点击保存')
      }
    } else {
      ElMessage.success(tryRepair ? '兼容修复检测完成' : '能力检测完成')
    }
  } catch (e: any) {
    ElMessage.error(`能力检测失败：${e?.message || e}`)
  } finally {
    capabilityLoading.value = false
  }
}

function applyCapabilityRecommendation() {
  if (!capabilityResult.value) return
  if (!canApplyCapabilityRecommendation.value) {
    ElMessage.warning('基础连接未通过，不能应用为普通写作/审核配置')
    return
  }
  applyCapabilityRecommendationToForm()
  ElMessage.success('已应用到当前表单，请保存后生效')
}

function applyCapabilityRecommendationToForm() {
  if (!capabilityResult.value) return
  const mode = capabilityResult.value.recommended_mode
  form.api_protocol = mode.api_protocol
  form.recommended_assistant_mode = mode.assistant_mode
  form.disable_stream = mode.disable_stream
  if (mode.use_default_user_agent && mode.recommended_user_agent) {
    form.user_agent = mode.recommended_user_agent
  }
  form.capability_summary = {
    overall: capabilityResult.value.overall,
    tests: capabilityResult.value.tests,
    tags: capabilityResult.value.tags,
    summary: capabilityResult.value.summary,
    recommended_mode: mode,
    repair_notes: capabilityResult.value.repair_notes,
  }
  form.capability_last_checked_at = new Date().toISOString()
  showAdvancedTransport.value = true
  showRareTransportFields.value = showRareTransportFields.value || !!form.user_agent
}

function statusTagType(status: string) {
  if (status === 'pass') return 'success'
  if (status === 'skip') return 'warning'
  return 'danger'
}

function statusText(status: string) {
  if (status === 'pass') return '通过'
  if (status === 'skip') return '跳过'
  return '失败'
}

function tagType(tag: string) {
  if (tag.includes('失败') || tag.includes('拦截') || tag.includes('不可用')) return 'danger'
  if (tag.includes('建议') || tag.includes('修复') || tag.includes('仅普通')) return 'warning'
  return 'success'
}

function overallText(overall: string) {
  const map: Record<string, string> = {
    full: '全功能',
    writing_review_only: '写作审核可用',
    react_assistant: 'ReAct助手可用',
    plain_only: '仅普通聊天',
    unusable: '不可用',
    unknown: '未知',
  }
  return map[overall] || overall
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

.capability-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
  min-width: 0;
}

.capability-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.capability-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-width: 0;
}

.capability-tags :deep(.el-tag) {
  max-width: 100%;
  height: auto;
  min-height: 24px;
  white-space: normal;
  line-height: 1.4;
  padding-top: 3px;
  padding-bottom: 3px;
}

.capability-tags :deep(.el-tag__content) {
  min-width: 0;
  overflow-wrap: anywhere;
  white-space: normal;
}

.capability-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 8px;
}

.capability-item {
  display: grid;
  grid-template-columns: 110px 56px minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.capability-name {
  font-size: 13px;
  color: var(--el-text-color-primary);
}

.capability-message {
  min-width: 0;
  overflow-wrap: anywhere;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.recommendation {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  min-width: 0;
  overflow-wrap: anywhere;
}
</style>
