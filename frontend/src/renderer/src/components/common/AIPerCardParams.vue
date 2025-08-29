<template>
	<div class="ai-param-inline">
		<el-popover placement="bottom" trigger="manual" v-model:visible="visible" width="360">
			<template #reference>
				<el-button type="primary" size="small" :icon="Setting" class="model-trigger" @click="visible = !visible">
					<span class="model-label">模型：</span>
					<span class="model-name">{{ selectedModelName || '未设置' }}</span>
				</el-button>
			</template>
			<div class="ai-config-form">
				<el-form label-width="92px" size="small">
					<el-form-item label="模型ID">
						<el-select v-model="editing.llm_config_id" placeholder="选择模型" style="width: 240px;" :teleported="false">
							<el-option v-for="m in (aiOptions?.llm_configs || [])" :key="m.id" :label="m.display_name || String(m.id)" :value="Number(m.id)" />
						</el-select>
					</el-form-item>
					<el-form-item label="提示词">
						<el-select v-model="editing.prompt_name" placeholder="选择提示词" filterable style="width: 240px;" :teleported="false">
							<el-option v-for="p in (aiOptions?.prompts || [])" :key="p.id" :label="p.name" :value="p.name" />
						</el-select>
					</el-form-item>
					<el-form-item label="温度">
						<el-input-number v-model="editing.temperature" :min="0" :max="2" :step="0.1" />
					</el-form-item>
					<el-form-item label="最大tokens">
						<el-input-number v-model="editing.max_tokens" :min="1" :step="256" />
					</el-form-item>
					<el-form-item label="超时(秒)">
						<el-input-number v-model="editing.timeout" :min="1" :step="5" />
					</el-form-item>
					<el-form-item>
						<div class="ai-actions">
							<div class="left">
								<el-button type="primary" size="small" @click="saveLocal">保存</el-button>
								<el-button size="small" @click="resetToPreset">重置为预设</el-button>
							</div>
							<div class="right">
								<el-button size="small" type="warning" plain @click="restoreFollowType">恢复跟随类型</el-button>
								<el-button size="small" type="primary" plain @click="applyToType">应用到类型</el-button>
							</div>
						</div>
					</el-form-item>
				</el-form>
			</div>
		</el-popover>
		<el-tooltip :content="summary" placement="top" :show-after="300" class="summary-tooltip">
			<el-tag size="small" effect="plain" class="param-summary">{{ summary }}</el-tag>
		</el-tooltip>
	</div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Setting } from '@element-plus/icons-vue'
import { usePerCardAISettingsStore, type PerCardAIParams } from '@renderer/stores/usePerCardAISettingsStore'
import { getAIConfigOptions, type AIConfigOptions } from '@renderer/api/ai'
import { getCardAIParams, updateCardAIParams, applyCardAIParamsToType } from '@renderer/api/setting'
import { ElMessage } from 'element-plus'

const props = defineProps<{ cardId: number; cardTypeName?: string }>()

const store = usePerCardAISettingsStore()
const visible = ref(false)
const aiOptions = ref<AIConfigOptions | null>(null)
const editing = ref<PerCardAIParams>({})

async function loadOptions() { try { aiOptions.value = await getAIConfigOptions() } catch {} }

const saved = computed(() => store.getByCardId(props.cardId))
const selectedModelName = computed(() => {
	try {
		const raw = (saved.value || editing.value)?.llm_config_id as any
		const id = raw == null ? undefined : Number(raw)
		const list = aiOptions.value?.llm_configs || []
		const found = list.find(m => Number(m.id) === id)
		return found?.display_name || (id != null ? String(id) : '')
	} catch { return '' }
})
const summary = computed(() => {
	const p = saved.value || editing.value
	const model = selectedModelName.value ? `模型:${selectedModelName.value}` : '模型:未设'
	const prompt = p?.prompt_name ? `任务:${p.prompt_name}` : '任务:未设'
	const t = p?.temperature != null ? `温度:${p.temperature}` : ''
	const m = p?.max_tokens != null ? `max_tokens:${p.max_tokens}` : ''
	return [model, prompt, t, m].filter(Boolean).join(' · ')
})

watch(() => props.cardId, async (id) => {
	if (!id) return
	await loadOptions()
	try {
		const resp = await getCardAIParams(id)
		const eff = (resp as any)?.effective_params
		if (eff && Object.keys(eff).length) {
			const fixed = { ...eff, llm_config_id: eff.llm_config_id == null ? eff.llm_config_id : Number(eff.llm_config_id) }
			editing.value = fixed
			store.setForCard(id, { ...fixed })
			return
		}
	} catch {}
	// fallback to saved or preset
	if (saved.value) {
		const sv = saved.value as any
		editing.value = { ...sv, llm_config_id: sv?.llm_config_id == null ? sv?.llm_config_id : Number(sv.llm_config_id) }
	} else {
		const preset = getPresetForType(props.cardTypeName)
		if (!preset.llm_config_id) {
			const first = aiOptions.value?.llm_configs?.[0]; if (first) preset.llm_config_id = Number(first.id)
		}
		editing.value = { ...preset, llm_config_id: preset.llm_config_id == null ? preset.llm_config_id : Number(preset.llm_config_id) }
		store.setForCard(id, editing.value)
	}
}, { immediate: true })

function getPresetForType(typeName?: string): PerCardAIParams {
	const map: Record<string, PerCardAIParams> = {
		'金手指': { prompt_name: '金手指生成', temperature: 0.6, max_tokens: 1024, timeout: 60 },
		'一句话梗概': { prompt_name: '一句话梗概', temperature: 0.6, max_tokens: 1024, timeout: 60 },
		'世界观设定': { prompt_name: '世界观设定', temperature: 0.6, max_tokens: 8192, timeout: 120 },
		'核心蓝图': { prompt_name: '核心蓝图', temperature: 0.6, max_tokens: 8192, timeout: 120 },
		'分卷大纲': { prompt_name: '分卷大纲', temperature: 0.6, max_tokens: 8192, timeout: 120 },
		'阶段大纲': { prompt_name: '阶段大纲', temperature: 0.6, max_tokens: 8192, timeout: 120 },
		'章节大纲': { prompt_name: '章节大纲', temperature: 0.6, max_tokens: 4096, timeout: 60 },
		'写作指南': { prompt_name: '写作指南', temperature: 0.7, max_tokens: 8192, timeout: 60 },
		'章节正文': { prompt_name: '内容生成', temperature: 0.7, max_tokens: 8192, timeout: 60 },
	}
	return map[typeName || ''] || {}
}

function saveLocal() {
	try {
		const payload = { ...editing.value, llm_config_id: editing.value.llm_config_id == null ? editing.value.llm_config_id : Number(editing.value.llm_config_id) }
		// 先写入后端数据库
		updateCardAIParams(props.cardId, payload)
			.then(() => {
				store.setForCard(props.cardId, { ...payload })
				ElMessage.success('已保存')
				visible.value = false
			})
			.catch(() => { ElMessage.error('保存到后端失败') })
	} catch { ElMessage.error('保存失败') }
}
function resetToPreset() {
	const preset = getPresetForType(props.cardTypeName)
	editing.value = { ...preset, llm_config_id: preset.llm_config_id == null ? preset.llm_config_id : Number(preset.llm_config_id) }
	store.setForCard(props.cardId, editing.value)
}
async function restoreFollowType() {
	try { await updateCardAIParams(props.cardId, null); ElMessage.success('已恢复跟随类型'); const resp = await getCardAIParams(props.cardId); const eff = (resp as any)?.effective_params; if (eff) { editing.value = { ...eff }; store.setForCard(props.cardId, { ...eff }) } } catch { ElMessage.error('操作失败') }
}
async function applyToType() {
	try {
		await updateCardAIParams(props.cardId, { ...editing.value })
		await applyCardAIParamsToType(props.cardId)
		window.dispatchEvent(new Event('card-types-updated'))
		await updateCardAIParams(props.cardId, null)
		const resp = await getCardAIParams(props.cardId)
		const eff = (resp as any)?.effective_params
		if (eff) { editing.value = { ...eff }; store.setForCard(props.cardId, { ...eff }) }
		ElMessage.success('已应用到类型，并恢复本卡片跟随类型')
	} catch { ElMessage.error('应用失败') }
}

</script>

<style scoped>
.ai-param-inline { display: inline-flex; align-items: center; gap: 8px; }
.summary-tooltip { display: inline-flex; align-items: center; }
.param-summary { display: inline-flex; align-items: center; height: 28px; line-height: 28px; max-width: 360px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.model-label { flex: 0 0 auto; }
.model-name { flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style> 