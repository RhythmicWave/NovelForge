<template>
	<div class="chapter-tools-panel">
		<div class="panel-toolbar">
			<el-popover
				v-model:visible="settingsVisible"
				placement="bottom-end"
				trigger="click"
				:width="360"
				@show="syncEditingConfigFromSaved"
			>
				<template #reference>
					<el-button class="config-trigger" type="primary" plain>
						<template #icon>
							<el-icon><Setting /></el-icon>
						</template>
						模型：{{ selectedModelName || '未设置' }}
					</el-button>
				</template>

				<el-form label-width="96px" size="small" class="config-form">
					<el-form-item label="模型">
						<el-select
							v-model="editingConfig.llm_config_id"
							placeholder="选择模型"
							filterable
							style="width: 100%;"
							:teleported="false"
						>
							<el-option
								v-for="llm in llmConfigs"
								:key="llm.id"
								:label="llm.display_name"
								:value="Number(llm.id)"
							/>
						</el-select>
					</el-form-item>
					<el-form-item label="温度">
						<el-input-number v-model="editingConfig.temperature" :min="0" :max="2" :step="0.1" />
					</el-form-item>
					<el-form-item label="最大tokens">
						<el-input-number v-model="editingConfig.max_tokens" :min="256" :max="32768" :step="256" />
					</el-form-item>
					<el-form-item label="超时(秒)">
						<el-input-number v-model="editingConfig.timeout" :min="10" :max="600" :step="10" />
					</el-form-item>
					<el-form-item>
						<div class="config-actions">
							<el-button type="primary" size="small" @click="saveConfig">保存</el-button>
							<el-button size="small" @click="resetEditingConfigToPreset">重置为预设</el-button>
						</div>
					</el-form-item>
				</el-form>
			</el-popover>
		</div>

		<div v-if="isBusy" class="busy-banner">
			<el-icon class="busy-icon is-loading"><Loading /></el-icon>
			<span>正在{{ runningActionLabel }}，完成后会自动打开预览。</span>
		</div>

		<el-card class="tool-card" shadow="never">
			<template #header>
				<div class="card-header">
					<el-icon><User /></el-icon>
					<span>角色动态信息</span>
				</div>
			</template>
			<div class="card-body">
				<el-button
					type="primary"
					class="action-button"
					:loading="runningAction === 'dynamic'"
					:disabled="isBusy && runningAction !== 'dynamic'"
					@click="handleExtractDynamicInfo"
				>
					提取角色动态
				</el-button>
			</div>
		</el-card>

		<el-card class="tool-card" shadow="never">
			<template #header>
				<div class="card-header">
					<el-icon><Connection /></el-icon>
					<span>关系提取入图</span>
				</div>
			</template>
			<div class="card-body">
				<el-button
					type="primary"
					class="action-button"
					:loading="runningAction === 'relations'"
					:disabled="isBusy && runningAction !== 'relations'"
					@click="handleExtractRelations"
				>
					提取关系入图
				</el-button>
			</div>
		</el-card>

		<el-card class="tool-card" shadow="never">
			<template #header>
				<div class="card-header">
					<el-icon><Box /></el-icon>
					<span>拓展记忆</span>
				</div>
			</template>
			<div class="card-body">
				<div class="memory-actions">
					<el-button
						type="primary"
						plain
						class="memory-button"
						:loading="runningAction === 'scene_state'"
						:disabled="isBusy && runningAction !== 'scene_state'"
						@click="handleExtractSceneState"
					>
						提取场景状态
					</el-button>
					<el-button
						type="primary"
						plain
						class="memory-button"
						:loading="runningAction === 'organization_state'"
						:disabled="isBusy && runningAction !== 'organization_state'"
						@click="handleExtractOrganizationState"
					>
						提取组织状态
					</el-button>
					<el-button
						type="primary"
						plain
						class="memory-button"
						:loading="runningAction === 'item_state'"
						:disabled="isBusy && runningAction !== 'item_state'"
						@click="handleExtractItemState"
					>
						提取物品状态
					</el-button>
					<el-button
						type="primary"
						plain
						class="memory-button"
						:loading="runningAction === 'concept_state'"
						:disabled="isBusy && runningAction !== 'concept_state'"
						@click="handleExtractConceptState"
					>
						提取概念掌握
					</el-button>
				</div>
			</div>
		</el-card>
	</div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { Box, Connection, Loading, Setting, User } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

import { getAIConfigOptions } from '@renderer/api/ai'
import { useEditorStore, type ChapterExtractRunOptions } from '@renderer/stores/useEditorStore'

type ExtractionAction =
	| ''
	| 'dynamic'
	| 'relations'
	| 'scene_state'
	| 'organization_state'
	| 'item_state'
	| 'concept_state'

interface ChapterExtractConfigState {
	llm_config_id: number | null
	temperature: number
	max_tokens: number
	timeout: number
}

const EXTRACT_CONFIG_STORAGE_KEY = 'nf:chapter:extract-panel-config'
const DEFAULT_EXTRACT_CONFIG = {
	llm_config_id: null,
	temperature: 0.7,
	max_tokens: 8192,
	timeout: 120,
} satisfies ChapterExtractConfigState

const editorStore = useEditorStore()

const llmConfigs = ref<Array<{ id: number; display_name: string }>>([])
const runningAction = ref<ExtractionAction>('')
const settingsVisible = ref(false)
const extractConfig = reactive<ChapterExtractConfigState>({ ...DEFAULT_EXTRACT_CONFIG })
const editingConfig = reactive<ChapterExtractConfigState>({ ...DEFAULT_EXTRACT_CONFIG })

const isBusy = computed(() => runningAction.value !== '')
const selectedModelName = computed(() => {
	const found = llmConfigs.value.find(item => Number(item.id) === Number(extractConfig.llm_config_id))
	return found?.display_name || ''
})

const runningActionLabel = computed(() => {
	switch (runningAction.value) {
		case 'dynamic':
			return '提取角色动态'
		case 'relations':
			return '提取关系入图'
		case 'scene_state':
			return '提取场景状态'
		case 'organization_state':
			return '提取组织状态'
		case 'item_state':
			return '提取物品状态'
		case 'concept_state':
			return '提取概念掌握'
		default:
			return '提取'
	}
})

function resolvePresetConfig(): ChapterExtractConfigState {
	return {
		...DEFAULT_EXTRACT_CONFIG,
		llm_config_id: llmConfigs.value.length > 0 ? Number(llmConfigs.value[0].id) : null,
	}
}

function sanitizeConfig(source?: Partial<ChapterExtractConfigState> | null): ChapterExtractConfigState {
	const modelIds = new Set(llmConfigs.value.map(item => Number(item.id)))
	const preset = resolvePresetConfig()
	const requestedModelId = source?.llm_config_id == null ? preset.llm_config_id : Number(source.llm_config_id)
	const llm_config_id =
		requestedModelId != null && modelIds.has(Number(requestedModelId))
			? Number(requestedModelId)
			: preset.llm_config_id

	return {
		llm_config_id,
		temperature:
			typeof source?.temperature === 'number'
				? Math.max(0, Math.min(2, source.temperature))
				: preset.temperature,
		max_tokens:
			typeof source?.max_tokens === 'number'
				? Math.max(256, Math.round(source.max_tokens))
				: preset.max_tokens,
		timeout:
			typeof source?.timeout === 'number'
				? Math.max(10, Math.round(source.timeout))
				: preset.timeout,
	}
}

function readSavedConfig(): Partial<ChapterExtractConfigState> {
	try {
		const raw = localStorage.getItem(EXTRACT_CONFIG_STORAGE_KEY)
		return raw ? JSON.parse(raw) : {}
	} catch {
		return {}
	}
}

function writeSavedConfig(config: ChapterExtractConfigState) {
	try {
		localStorage.setItem(EXTRACT_CONFIG_STORAGE_KEY, JSON.stringify(config))
	} catch {}
}

function hydrateConfig() {
	Object.assign(extractConfig, sanitizeConfig(readSavedConfig()))
	syncEditingConfigFromSaved()
}

function syncEditingConfigFromSaved() {
	Object.assign(editingConfig, extractConfig)
}

function resetEditingConfigToPreset() {
	Object.assign(editingConfig, resolvePresetConfig())
}

function saveConfig() {
	const nextConfig = sanitizeConfig(editingConfig)
	if (!nextConfig.llm_config_id) {
		ElMessage.warning('请先选择模型')
		return
	}
	Object.assign(extractConfig, nextConfig)
	writeSavedConfig(nextConfig)
	settingsVisible.value = false
	ElMessage.success('提取模型配置已保存到本地')
}

function buildExtractOptions(): ChapterExtractRunOptions | null {
	if (!extractConfig.llm_config_id) {
		ElMessage.warning('请先选择模型')
		return null
	}
	return {
		llm_config_id: Number(extractConfig.llm_config_id),
		temperature: extractConfig.temperature,
		max_tokens: Math.round(extractConfig.max_tokens),
		timeout: Math.round(extractConfig.timeout),
	}
}

async function runExtraction(
	action: Exclude<ExtractionAction, ''>,
	runner: (options: ChapterExtractRunOptions) => Promise<void>
) {
	if (runningAction.value) return
	const options = buildExtractOptions()
	if (!options) return
	runningAction.value = action
	try {
		await runner(options)
	} catch (error) {
		console.error(`[ChapterToolsPanel] ${action} failed:`, error)
	} finally {
		runningAction.value = ''
	}
}

async function handleExtractDynamicInfo() {
	await runExtraction('dynamic', options => editorStore.triggerExtractDynamicInfo(options))
}

async function handleExtractRelations() {
	await runExtraction('relations', options => editorStore.triggerExtractRelations(options))
}

async function handleExtractSceneState() {
	await runExtraction('scene_state', options => editorStore.triggerExtractSceneState(options))
}

async function handleExtractOrganizationState() {
	await runExtraction('organization_state', options => editorStore.triggerExtractOrganizationState(options))
}

async function handleExtractItemState() {
	await runExtraction('item_state', options => editorStore.triggerExtractItemState(options))
}

async function handleExtractConceptState() {
	await runExtraction('concept_state', options => editorStore.triggerExtractConceptState(options))
}

onMounted(async () => {
	try {
		const options = await getAIConfigOptions()
		llmConfigs.value = options?.llm_configs || []
	} catch (error) {
		console.error('Failed to load LLM configs:', error)
	}
	hydrateConfig()
})
</script>

<style scoped>
.chapter-tools-panel {
	padding: 16px;
	display: flex;
	flex-direction: column;
	gap: 14px;
	height: 100%;
	overflow-y: auto;
	background: linear-gradient(180deg, rgba(248, 250, 252, 0.94) 0%, rgba(255, 255, 255, 0.98) 100%);
}

.panel-toolbar {
	display: flex;
	justify-content: flex-start;
}

.config-trigger {
	min-width: 144px;
}

.config-form {
	padding-top: 4px;
}

.config-actions {
	width: 100%;
	display: flex;
	align-items: center;
	justify-content: flex-end;
	gap: 8px;
}

.tool-card {
	border-radius: 14px;
	border: 1px solid rgba(15, 23, 42, 0.08);
	box-shadow: 0 8px 24px rgba(15, 23, 42, 0.05);
}

.busy-banner {
	display: flex;
	align-items: center;
	gap: 8px;
	padding: 10px 12px;
	border-radius: 12px;
	background: rgba(37, 99, 235, 0.08);
	color: #1d4ed8;
	font-size: 13px;
}

.busy-icon {
	font-size: 16px;
}

.card-header {
	display: flex;
	align-items: center;
	gap: 8px;
	font-weight: 700;
	color: var(--el-text-color-primary);
}

.card-body {
	display: flex;
	flex-direction: column;
	gap: 12px;
}

.action-button {
	width: 100%;
}

.memory-actions {
	display: grid;
	grid-template-columns: repeat(2, minmax(0, 1fr));
	gap: 10px;
}

.memory-button {
	width: 100%;
	margin-left: 0;
}

@media (max-width: 900px) {
	.panel-toolbar {
		justify-content: stretch;
	}

	.config-trigger {
		width: 100%;
	}

	.memory-actions {
		grid-template-columns: minmax(0, 1fr);
	}
}
</style>
