<script setup lang="ts">
import { ref } from 'vue'
import LLMConfigManager from '../setting/LLMConfigManager.vue'
// import Versions from '../Versions.vue'
import PromptWorkshop from '../setting/PromptWorkshop.vue'
import AIParamCardManager from '../setting/AIParamCardManager.vue'
import CardTypeManager from '../setting/CardTypeManager.vue'
import OutputModelManager from '../setting/OutputModelManager.vue'
import KnowledgeManager from '../setting/KnowledgeManager.vue'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean]; 'close': [] }>()

const activeTab = ref('llm')

function handleClose() {
  emit('update:modelValue', false)
  emit('close')
}
</script>

<template>
  <el-dialog 
    :model-value="modelValue" 
    @update:model-value="(val) => emit('update:modelValue', val)"
    title="应用设置" 
    width="85%" 
    top="4vh"
    @close="handleClose"
  >
    <div class="settings-container">
      <el-tabs v-model="activeTab" tab-position="left" class="settings-tabs">
        <el-tab-pane label="LLM 配置" name="llm">
          <LLMConfigManager />
        </el-tab-pane>
        <el-tab-pane label="知识库" name="knowledge">
          <KnowledgeManager />
        </el-tab-pane>
        <el-tab-pane label="提示词工坊" name="prompts">
          <PromptWorkshop />
        </el-tab-pane>
        <el-tab-pane label="AI参数卡片" name="ai-cards">
          <AIParamCardManager />
        </el-tab-pane>
        <el-tab-pane label="输出模型" name="output-models">
          <OutputModelManager />
        </el-tab-pane>
        <el-tab-pane label="卡片类型" name="card-types">
          <CardTypeManager />
        </el-tab-pane>
        <!-- <el-tab-pane label="关于" name="about">
          <Versions />
        </el-tab-pane> -->
      </el-tabs>
    </div>
  </el-dialog>
</template>

<style scoped>
.settings-container { height: 78vh; }
.settings-tabs { height: 100%; }
:deep(.el-dialog__body) { padding-top: 8px; }
:deep(.el-tabs__content) { height: 100%; overflow-y: auto; }
</style> 