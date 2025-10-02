<template>
	<div class="chapter-tools-panel">
		<!-- 角色动态信息提取 -->
		<el-card class="tool-card" shadow="never">
			<template #header>
				<div class="card-header">
					<el-icon><User /></el-icon>
					<span>角色动态信息</span>
				</div>
			</template>
			
			<el-form label-width="100px" size="default">
				<el-form-item label="使用模型">
					<el-select v-model="dynamicInfoLLM" placeholder="选择模型">
						<el-option 
							v-for="llm in llmConfigs" 
							:key="llm.id"
							:label="llm.display_name" 
							:value="llm.id" 
						/>
					</el-select>
				</el-form-item>
				
				<el-form-item label="预览后更新">
					<el-switch v-model="previewBeforeUpdate" />
				</el-form-item>
				
				<el-form-item>
					<el-button 
						type="primary" 
						:loading="extractingDynamic"
						@click="handleExtractDynamicInfo"
					>提取动态信息</el-button>
				</el-form-item>
			</el-form>
		</el-card>

		<!-- 关系提取入图 -->
		<el-card class="tool-card" shadow="never">
			<template #header>
				<div class="card-header">
					<el-icon><Connection /></el-icon>
					<span>关系提取入图</span>
				</div>
			</template>
			
			<el-form label-width="100px" size="default">
				<el-form-item label="使用模型">
					<el-select v-model="relationsLLM" placeholder="选择模型">
						<el-option 
							v-for="llm in llmConfigs" 
							:key="llm.id"
							:label="llm.display_name" 
							:value="llm.id" 
						/>
					</el-select>
				</el-form-item>
				
				<el-form-item>
					<el-button 
						type="primary" 
						:loading="extractingRelations"
						@click="handleExtractRelations"
					>提取关系入图</el-button>
				</el-form-item>
			</el-form>
		</el-card>
	</div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { User, Connection } from '@element-plus/icons-vue'
import { getAIConfigOptions, type AIConfigOptions } from '@renderer/api/ai'
import { useEditorStore } from '@renderer/stores/useEditorStore'
import { ElMessage } from 'element-plus'

const editorStore = useEditorStore()

const dynamicInfoLLM = ref<number | null>(null)
const relationsLLM = ref<number | null>(null)
const extractingDynamic = ref(false)
const extractingRelations = ref(false)
const previewBeforeUpdate = ref(true)
const llmConfigs = ref<any[]>([])

onMounted(async () => {
	try {
		const options = await getAIConfigOptions()
		llmConfigs.value = options?.llm_configs || []
		if (llmConfigs.value.length > 0) {
			dynamicInfoLLM.value = llmConfigs.value[0].id
			relationsLLM.value = llmConfigs.value[0].id
		}
	} catch (e) {
		console.error('Failed to load LLM configs:', e)
	}
})

async function handleExtractDynamicInfo() {
	if (!dynamicInfoLLM.value) {
		ElMessage.warning('请选择模型')
		return
	}
	extractingDynamic.value = true
	try {
		await editorStore.triggerExtractDynamicInfo({ 
			llm_config_id: dynamicInfoLLM.value,
			preview: previewBeforeUpdate.value
		})
	} catch (e) {
		console.error('提取动态信息失败:', e)
	} finally {
		extractingDynamic.value = false
	}
}

async function handleExtractRelations() {
	if (!relationsLLM.value) {
		ElMessage.warning('请选择模型')
		return
	}
	extractingRelations.value = true
	try {
		// 发送自定义事件给 CodeMirrorEditor
		window.dispatchEvent(new CustomEvent('nf:extract-relations', { 
			detail: { llm_config_id: relationsLLM.value } 
		}))
		// 延迟重置 loading，等待提取完成
		setTimeout(() => {
			extractingRelations.value = false
		}, 1000)
	} catch (e) {
		console.error('提取关系失败:', e)
		extractingRelations.value = false
	}
}
</script>

<style scoped>
.chapter-tools-panel {
	padding: 16px;
	display: flex;
	flex-direction: column;
	gap: 16px;
	height: 100%;
	overflow-y: auto;
}

.tool-card {
	border-radius: 8px;
}

.card-header {
	display: flex;
	align-items: center;
	gap: 8px;
	font-weight: 600;
	color: var(--el-text-color-primary);
}
</style>

