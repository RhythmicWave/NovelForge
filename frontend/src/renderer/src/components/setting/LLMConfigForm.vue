
<template>
  <el-form :model="form" ref="formRef" :rules="rules" label-width="100px">
    <el-form-item label="提供商" prop="provider">
      <el-select v-model="form.provider" placeholder="请选择提供商">
        <el-option label="OpenAI兼容" value="openai_compatible" />
        <el-option label="OpenAI" value="openai" />
        <el-option label="Google" value="google" />
        <el-option label="Anthropic" value="anthropic" />
      </el-select>
    </el-form-item>
    <el-form-item label="模型名称" prop="model_name">
      <el-input v-model="form.model_name" placeholder="例如: moonshotai/Kimi-K2-Instruct" />
    </el-form-item>
    <el-form-item label="显示名称" prop="display_name">
      <el-input v-model="form.display_name" placeholder="可选, 留空时将自动使用模型名称" />
    </el-form-item>
    <el-form-item label="API Base" prop="api_base">
      <el-input
        v-model="form.api_base"
        :disabled="form.provider !== 'openai_compatible'"
        placeholder="例如: https://api.siliconflow.cn/v1（仅 OpenAI兼容 使用）"
      />
    </el-form-item>
    <el-form-item label="API Key" prop="api_key">
      <el-input type="password" v-model="form.api_key" placeholder="API密钥将直接保存在后端" show-password />
    </el-form-item>
    <el-form-item label="Token上限" prop="token_limit">
      <el-input-number v-model="form.token_limit" :min="-1" :step="1000" />
      <span style="margin-left:8px;color:#888">-1 表示不限</span>
    </el-form-item>
    <el-form-item label="调用次数上限" prop="call_limit">
      <el-input-number v-model="form.call_limit" :min="-1" />
      <span style="margin-left:8px;color:#888">-1 表示不限</span>
    </el-form-item>
    <el-form-item>
      <el-button @click="handleCancel">取消</el-button>
      <el-button type="primary" @click="handleSubmit">保存</el-button>
      <el-button @click="handleTest">测试连接</el-button>
    </el-form-item>
  </el-form>
</template>

<script setup lang="ts">
import { ref, reactive, watch } from 'vue'
import type { components } from '@renderer/types/generated'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'
import { testLLMConnection } from '@renderer/api/setting'

type LLMConfig = components['schemas']['LLMConfigRead']

const props = defineProps<{
  initialData?: LLMConfig | null
}>()

const emit = defineEmits(['save', 'cancel'])
const formRef = ref<FormInstance>()

const form = reactive({
  id: null as number | null,
  provider: 'openai_compatible',
  display_name: '',
  model_name: '',
  api_base: '',
  api_key: '',
  token_limit: -1 as number,
  call_limit: -1 as number,
})

const rules = reactive<FormRules>({
  provider: [{ required: true, message: '请选择提供商', trigger: 'change' }],
  model_name: [{ required: true, message: '请输入模型名称', trigger: 'blur' }],
  api_key: [{ required: true, message: '请输入API Key', trigger: 'blur' }]
})

watch(() => props.initialData, (newData) => {
  if (newData) {
    // 编辑现有配置
    form.id = newData.id;
    form.provider = newData.provider;
    form.display_name = newData.display_name || '';
    form.model_name = newData.model_name;
    form.api_base = newData.api_base || '';
    form.api_key = newData.api_key || '';
    form.token_limit = (newData as any).token_limit ?? -1;
    form.call_limit = (newData as any).call_limit ?? -1;
  } else {
    // 新增配置，重置表单
    form.id = null;
    form.provider = 'openai_compatible';
    form.display_name = '';
    form.model_name = '';
    form.api_base = '';
    form.api_key = '';
    form.token_limit = -1;
    form.call_limit = -1;
  }
}, { immediate: true })



async function handleSubmit() {
  const valid = await formRef.value?.validate()
  if (valid) {
    emit('save', form)
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
      api_base: form.api_base || undefined,
      api_key: form.api_key
    } as any)
    ElMessage.success('连接成功')
  } catch (e:any) {
    ElMessage.error(`连接失败：${e?.message || e}`)
  }
}

</script> 