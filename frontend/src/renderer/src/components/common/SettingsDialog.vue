<script setup lang="ts">
import { ref, onMounted } from 'vue'
import LLMConfigManager from '../setting/LLMConfigManager.vue'
import Versions from '../Versions.vue'
import PromptWorkshop from '../setting/PromptWorkshop.vue'
import AIParamCardManager from '../setting/AIParamCardManager.vue'
import CardTypeManager from '../setting/CardTypeManager.vue'
import OutputModelManager from '../setting/OutputModelManager.vue'
import { getContextSettings, updateContextSettings, type ContextSettingsModel } from '@renderer/api/ai'
import { ElMessage } from 'element-plus'
import { useConsistencySettingsStore } from '@renderer/stores/useConsistencySettingsStore'
// 移除 KnowledgeManager 引入

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean]; 'close': [] }>()

const activeTab = ref('llm')

function handleClose() {
  emit('update:modelValue', false)
  emit('close')
}

// 上下文设置表单
const ctxForm = ref<ContextSettingsModel | null>(null)
const ctxLoading = ref(false)

async function loadCtx() {
  try {
    ctxLoading.value = true
    ctxForm.value = await getContextSettings()
  } catch (e:any) {
    ElMessage.error('加载上下文设置失败')
  } finally {
    ctxLoading.value = false
  }
}

async function saveCtx() {
  if (!ctxForm.value) return
  try {
    ctxLoading.value = true
    const saved = await updateContextSettings(ctxForm.value)
    ctxForm.value = saved
    ElMessage.success('已保存上下文设置')
  } catch (e:any) {
    ElMessage.error('保存失败')
  } finally {
    ctxLoading.value = false
  }
}

// 一致性设置（前端本地）
const consistencyStore = useConsistencySettingsStore()
consistencyStore.loadFromLocal()

function saveConsistency() {
  consistencyStore.saveToLocal()
  ElMessage.success('一致性设置已保存（本地）')
}

onMounted(() => {
  loadCtx()
})
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
        <!-- 移除 知识库 页签 -->
        <el-tab-pane label="上下文设置" name="context-settings">
          <div v-loading="ctxLoading" class="ctx-panel">
            <el-form v-if="ctxForm" :model="ctxForm" label-width="220px">
              <el-form-item label="最近章节窗口（N）">
                <el-input-number v-model="ctxForm.recent_chapters_window" :min="1" :max="5" />
              </el-form-item>
              <el-form-item label="总预算上限（字符）">
                <el-input-number v-model="ctxForm.total_context_budget_chars" :min="10000" :step="1000" />
              </el-form-item>
              <el-form-item label="软阈（字符）">
                <el-input-number v-model="ctxForm.soft_budget_chars" :min="10000" :step="1000" />
              </el-form-item>
              <el-divider>配额</el-divider>
              <el-form-item label="最近章节文本配额">
                <el-input-number v-model="ctxForm.quota_recent" :min="1000" :step="500" />
              </el-form-item>
              <el-form-item label="更早章节摘要配额">
                <el-input-number v-model="ctxForm.quota_older_summary" :min="1000" :step="500" />
              </el-form-item>
              <el-form-item label="事实子图配额">
                <el-input-number v-model="ctxForm.quota_facts" :min="500" :step="500" />
              </el-form-item>
              <el-form-item>
                <el-button type="primary" @click="saveCtx">保存</el-button>
                <el-button @click="loadCtx">重载</el-button>
              </el-form-item>
            </el-form>
          </div>
        </el-tab-pane>
        <el-tab-pane label="知识一致性" name="consistency">
          <div class="ctx-panel">
            <el-form :model="consistencyStore.settings" label-width="220px">
              <el-form-item label="启用知识图谱一致性">
                <el-switch v-model="consistencyStore.settings.kg_enabled" />
              </el-form-item>
              <el-form-item label="一致性模式">
                <el-select v-model="consistencyStore.settings.consistency_mode" style="width: 220px">
                  <el-option label="关闭" value="off" />
                  <el-option label="轻量" value="light" />
                  <el-option label="严格" value="strict" />
                </el-select>
              </el-form-item>
              <el-divider>触发策略</el-divider>
              <el-form-item label="每窗口N章触发">
                <el-switch v-model="consistencyStore.settings.kg_trigger.on_chapter_window_close.enabled" />
                <span style="margin-left:12px">窗口 N：</span>
                <el-input-number v-model="consistencyStore.settings.kg_trigger.on_chapter_window_close.window_size" :min="1" :max="10" />
              </el-form-item>
              <el-form-item label="大纲关键字段变更触发">
                <el-switch v-model="consistencyStore.settings.kg_trigger.on_outline_change.enabled" />
              </el-form-item>
              <el-form-item label="定时触发">
                <el-switch v-model="consistencyStore.settings.kg_trigger.cron.enabled" />
                <el-input v-model="consistencyStore.settings.kg_trigger.cron.expr" placeholder="CRON 表达式" style="width: 240px; margin-left: 12px" />
              </el-form-item>
              <el-form-item label="手动触发">
                <el-switch v-model="consistencyStore.settings.kg_trigger.manual.enabled" />
              </el-form-item>
              <el-divider>功能项</el-divider>
              <el-form-item label="别名/称谓">
                <el-switch v-model="consistencyStore.settings.kg_features.aliases" />
              </el-form-item>
              <el-form-item label="状态快照（境界/财富）">
                <el-switch v-model="consistencyStore.settings.kg_features.state_snapshots" />
              </el-form-item>
              <el-form-item label="关系">
                <el-select v-model="consistencyStore.settings.kg_features.relations" style="width: 220px">
                  <el-option label="无" value="none" />
                  <el-option label="基础" value="basic" />
                  <el-option label="完整" value="full" />
                </el-select>
              </el-form-item>
              <el-divider>成本预算</el-divider>
              <el-form-item label="每次构建最多 LLM 调用">
                <el-input-number v-model="consistencyStore.settings.kg_cost_budget.llm_calls_per_build" :min="0" :max="10" />
              </el-form-item>
              <el-form-item label="使用 Embedding">
                <el-switch v-model="consistencyStore.settings.kg_cost_budget.use_embedding" />
              </el-form-item>
              <el-form-item label="使用 Reranker">
                <el-switch v-model="consistencyStore.settings.kg_cost_budget.use_reranker" />
              </el-form-item>
              <el-form-item>
                <el-button type="primary" @click="saveConsistency">保存（本地）</el-button>
              </el-form-item>
            </el-form>
          </div>
        </el-tab-pane>
        <el-tab-pane label="关于" name="about">
          <Versions />
        </el-tab-pane>
      </el-tabs>
    </div>
  </el-dialog>
</template>

<style scoped>
.settings-container { height: 78vh; }
.settings-tabs { height: 100%; }
.ctx-panel { padding: 12px 16px; }
:deep(.el-dialog__body) { padding-top: 8px; }
:deep(.el-tabs__content) { height: 100%; overflow-y: auto; }
</style> 