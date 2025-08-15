<template>
	<div v-if="editor" class="editor-container">
		<div class="toolbar">
			<el-button-group>
				<el-tooltip content="加粗 (Ctrl+B)" placement="bottom">
					<el-button :type="editor.isActive('bold') ? 'primary' : ''" @click="editor.chain().focus().toggleBold().run()">B</el-button>
				</el-tooltip>
				<el-tooltip content="斜体 (Ctrl+I)" placement="bottom">
					<el-button :type="editor.isActive('italic') ? 'primary' : ''" @click="editor.chain().focus().toggleItalic().run()">I</el-button>
				</el-tooltip>
				<el-tooltip content="下划线 (Ctrl+U)" placement="bottom">
					<el-button :type="editor.isActive('underline') ? 'primary' : ''" @click="editor.chain().focus().toggleUnderline().run()">U</el-button>
				</el-tooltip>
				<el-tooltip content="高亮" placement="bottom">
					 <el-button :type="editor.isActive('highlight') ? 'primary' : ''" @click="editor.chain().focus().toggleHighlight().run()">Hl</el-button>
				</el-tooltip>
			</el-button-group>

			<el-button-group class="mx-2">
				<el-tooltip content="自动缩进" placement="bottom">
					<el-button :type="autoIndent ? 'primary' : ''" @click="toggleAutoIndent">缩进</el-button>
				</el-tooltip>
			</el-button-group>

			<div class="flex-spacer"></div>

			<span class="word-count-display">{{ wordCount }} 字</span>

			<el-popover placement="bottom-end" title="AI续写设置" :width="400" trigger="click">
				<!-- 预留更多设置项 -->
			</el-popover>
			
			<el-button @click="openDrawer = true" plain>上下文注入</el-button>
			<el-button @click="executeAIContinuation" type="primary" :loading="aiLoading">
				AI续写
			</el-button>
			<el-button @click="interruptStream" :disabled="!streamHandle" type="danger">
				中断
			</el-button>
			<el-button @click="handleSave" type="success" class="ml-2">
				保存
			</el-button>
			<el-button @click="handleIngestRelations" class="ml-2">
				入图关系
			</el-button>
		</div>
		<div class="editor-content-wrapper">
			<div class="chapter-title-display">
				<div class="chapter-title-wrapper">
					<h1 class="chapter-title-text">{{ localCard.title }}</h1>
					<!-- 将参数卡选择放到标题区域右侧空白处 -->
					<div class="title-actions">
						<el-select v-model="selectedAiParamCardId" placeholder="选择参数卡" class="param-select-top" @change="onParamChange" filterable>
							<el-option v-for="p in paramCards" :key="p.id" :label="p.name || ('参数卡 ' + p.id)" :value="p.id" />
						</el-select>
					</div>
				</div>
			</div>
			<EditorContent :editor="editor" class="editor-content" @keydown="handleKeydown" />
		</div>

		<ContextDrawer
			v-model="openDrawer"
			:context-template="contextTemplate"
			:preview-text="editorText"
			@apply-context="onApplyContext"
			@open-selector="openReferenceSelector"
		/>
		<CardReferenceSelectorDialog
			v-model="openSelector"
			:cards="cards"
			:current-card-id="localCard.id"
			@confirm="handleSelectorConfirm"
		/>

		<el-dialog v-model="previewDialogVisible" title="动态信息预览" width="70%">
			<div v-if="previewData">
				<div v-for="role in previewData.info_list" :key="role.name" class="role-block">
					<h4>{{ role.name }}</h4>
					<div v-for="(items, catKey) in role.dynamic_info" :key="String(catKey)" class="cat-block">
						<div class="cat-title">{{ formatCategory(catKey) }}</div>
						<el-table :data="items as any[]" size="small" border>
							<el-table-column prop="id" label="ID" width="60" />
							<el-table-column prop="info" label="信息" min-width="360" />
							<el-table-column prop="weight" label="权重(0~1)" width="160">
								<template #default="{ row }">
									<el-input-number v-model="row.weight" :min="0" :max="1" :step="0.1" />
								</template>
							</el-table-column>
							<el-table-column label="操作" width="90">
								<template #default="scope">
									<el-button type="danger" text size="small" @click="removePreviewItem(role.name, String(catKey), scope.$index)">删除</el-button>
								</template>
							</el-table-column>
						</el-table>
					</div>
				</div>
			</div>
			<template #footer>
				<el-button @click="previewDialogVisible=false">取消</el-button>
				<el-button type="primary" @click="confirmApplyUpdates">确定更新</el-button>
			</template>
		</el-dialog>

		<!-- 关系预览对话框 -->
		<el-dialog v-model="relationsPreviewVisible" title="关系入图预览" width="70%">
			<div v-if="relationsPreview">
				<div style="margin-top: 16px" v-if="relationsPreview.relations?.length">
					<h4>关系项</h4>
					<el-table :data="relationsPreview.relations" size="small" border>
						<el-table-column prop="a" label="A" width="160" />
						<el-table-column prop="kind" label="关系" width="120" />
						<el-table-column prop="b" label="B" width="160" />
						<el-table-column label="证据">
							<template #default="{ row }">
								<div v-if="row.a_to_b_addressing || row.b_to_a_addressing">
									<div v-if="row.a_to_b_addressing">A称呼B: {{ row.a_to_b_addressing }}</div>
									<div v-if="row.b_to_a_addressing">B称呼A: {{ row.b_to_a_addressing }}</div>
								</div>
								<div v-if="row.recent_dialogues?.length">
									<div>对话样例：</div>
									<ul style="margin: 4px 0 0 16px; padding: 0;">
										<li v-for="(d, i) in row.recent_dialogues" :key="i" style="list-style: disc;">
											{{ d }}
										</li>
									</ul>
								</div>
								<div v-if="row.recent_event_summaries?.length">
									<div>
										近期事件：{{ row.recent_event_summaries[ row.recent_event_summaries.length - 1 ].summary }}
										<span v-if="row.recent_event_summaries[row.recent_event_summaries.length-1].volume_number != null || row.recent_event_summaries[row.recent_event_summaries.length-1].chapter_number != null" style="color:#909399;margin-left:8px;">
											（卷{{ row.recent_event_summaries[row.recent_event_summaries.length-1].volume_number ?? '-' }}·章{{ row.recent_event_summaries[row.recent_event_summaries.length-1].chapter_number ?? '-' }}）
										</span>
									</div>
								</div>
							</template>
						</el-table-column>
					</el-table>
				</div>
			</div>
			<template #footer>
				<el-button @click="relationsPreviewVisible=false">取消</el-button>
				<el-button type="primary" @click="confirmIngestRelationsFromPreview">确认入图</el-button>
			</template>
		</el-dialog>
	</div>
</template>

<script setup lang="ts">
import { useEditor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Underline from '@tiptap/extension-underline'
import Highlight from '@tiptap/extension-highlight'
import TextAlign from '@tiptap/extension-text-align'
import { watch, onUnmounted, ref, reactive, computed } from 'vue'
import { generateContinuationStreaming, type ContinuationRequest } from '@renderer/api/ai'
import type { CardRead, CardUpdate } from '@renderer/api/cards'
import { useCardStore } from '@renderer/stores/useCardStore'
import { useProjectStore } from '@renderer/stores/useProjectStore'
import { useConsistencySettingsStore } from '@renderer/stores/useConsistencySettingsStore'
import { useConsistencyRuntimeStore } from '@renderer/stores/useConsistencyRuntimeStore'
import { useAIParamCardStore } from '@renderer/stores/useAIParamCardStore'
import { useEditorStore } from '@renderer/stores/useEditorStore'
import { ElMessage } from 'element-plus'
import ContextDrawer from '../common/ContextDrawer.vue'
import CardReferenceSelectorDialog from '../cards/CardReferenceSelectorDialog.vue'
import { storeToRefs } from 'pinia'
import { unwrapChapterOutline, extractParticipantsFrom } from '@renderer/services/contextHelpers'
import { resolveTemplate } from '@renderer/services/contextResolver'
import { extractDynamicInfoOnly, updateDynamicInfoOnly, type UpdateDynamicInfoOutput, extractRelationsOnly, ingestRelationsFromPreview, type RelationExtractionOutput } from '@renderer/api/memory'
import { assembleContext } from '@renderer/api/ai'

const props = defineProps<{ card: CardRead; chapter?: any; contextParams?: { project_id?: number; volume_number?: number; chapter_number?: number; participants?: string[]; extra_context_fn?: Function } }>()
const emit = defineEmits<{ (e: 'update:chapter', value: any): void; (e: 'save'): void }>()

const cardStore = useCardStore()
const projectStore = useProjectStore()
const consistencySettings = useConsistencySettingsStore()
const consistencyRuntime = useConsistencyRuntimeStore()
consistencyRuntime.load()
const aiParamCardStore = useAIParamCardStore()
const editorStore = useEditorStore()
const { cards } = storeToRefs(cardStore)
const { paramCards } = storeToRefs(aiParamCardStore)

// 当前选中的参数卡ID（来源于卡片的 selected_ai_param_card_id）
const selectedAiParamCardId = ref<string | undefined>(props.card.selected_ai_param_card_id ?? undefined)
watch(() => props.card.selected_ai_param_card_id, (id) => {
	selectedAiParamCardId.value = id ?? undefined
})

function onParamChange() {
	// 切换参数卡时立即回写，保持与通用编辑器一致
	cardStore.modifyCard(localCard.id, { selected_ai_param_card_id: selectedAiParamCardId.value } as any, { skipHooks: true })
}

// 确保本地卡片与内容结构
const localCard = reactive({ 
	...props.card,
	content: {
		// Chapter 模型：正文纯文本（优先使用父传 chapter）
		content: typeof (props.chapter as any)?.content === 'string'
			? (props.chapter as any).content
			: (typeof (props.card.content as any)?.content === 'string' ? (props.card.content as any).content : ''),
		word_count: typeof (props.chapter as any)?.content === 'string' ? ((props.chapter as any).content as string).length : (typeof (props.card.content as any)?.word_count === 'number' ? (props.card.content as any).word_count : 0),
		volume_number: (props.chapter as any)?.volume_number ?? ((props.contextParams as any)?.volume_number ?? ((props.card.content as any)?.volume_number ?? undefined)),
		chapter_number: (props.chapter as any)?.chapter_number ?? ((props.contextParams as any)?.chapter_number ?? ((props.card.content as any)?.chapter_number ?? undefined)),
		title: (props.chapter as any)?.title ?? ((props.card.content as any)?.title ?? props.card.title ?? ''),
		entity_list: (props.chapter as any)?.entity_list ?? ((props.card.content as any)?.entity_list ?? []),
		...(props.card.content as any || {})
	}
})
// 父级 chapter 变化时，同步到本地
watch(() => props.chapter, (ch) => {
	if (!ch) return
	const c: any = ch
	localCard.content = {
		...(localCard.content || {}),
		content: typeof c.content === 'string' ? c.content : (localCard.content as any)?.content || '',
		word_count: typeof c.content === 'string' ? c.content.length : (localCard.content as any)?.word_count || 0,
		volume_number: c.volume_number ?? (localCard.content as any)?.volume_number,
		chapter_number: c.chapter_number ?? (localCard.content as any)?.chapter_number,
		title: c.title ?? (localCard.content as any)?.title ?? props.card.title,
		entity_list: Array.isArray(c.entity_list) ? c.entity_list : ((localCard.content as any)?.entity_list || []),
	}
}, { deep: true })

const editor = useEditor({
	content: (() => {
		const txt = (localCard.content?.content as any) || ''
		// 将纯文本转为简单HTML段落
		const html = `<p>${String(txt).split('\n').map(l => l || '<br>').join('</p><p>')}</p>`
		return html
	})(),
	extensions: [
		StarterKit.configure({ underline: false }),
		Underline,
		Highlight,
		TextAlign.configure({ types: ['heading', 'paragraph'] }),
	],
})

// 注册跨组件替换接口
editorStore.setApplyChapterReplacements(async (pairs) => {
	if (!editor.value) return
	const original = editor.value.getText() || ''
	let replaced = original
	for (const { from, to } of pairs) {
		if (!from) continue
		// 全局替换（文本级，简单实现）
		const safeFrom = from.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
		replaced = replaced.replace(new RegExp(safeFrom, 'g'), to)
	}
	// 将替换的纯文本写回为简单段落
	editor.value.commands.setContent(`<p>${replaced.split('\n').map(l => l || '<br>').join('</p><p>')}</p>`, { emitUpdate: true })
})

const wordCount = ref(0)
const autoIndent = ref(false)
const aiLoading = ref(false)
let streamHandle: { cancel: () => void } | null = null
const openDrawer = ref(false)
const editorText = computed(() => editor.value?.getText() || '')
const contextTemplate = ref('')
// 初始：若卡片已有模板，填充
watch(() => props.card, (c) => { if (c && (c as any).ai_context_template != null) contextTemplate.value = String((c as any).ai_context_template || '') }, { immediate: true })
const openSelector = ref(false)
const previewBeforeUpdate = ref(true)
const previewDialogVisible = ref(false)
const previewData = ref<UpdateDynamicInfoOutput | null>(null)
const relationsPreviewVisible = ref(false)
const relationsPreview = ref<RelationExtractionOutput | null>(null)

function formatCategory(catKey: any) {
	// catKey 可能是枚举的值字符串
	return String(catKey)
}

// 允许外部触发“动态信息提取”（供右栏调用）
editorStore.setTriggerExtractDynamicInfo(async (opts) => {
	if (typeof opts?.preview === 'boolean') previewBeforeUpdate.value = !!opts.preview
	if (typeof opts?.llm_config_id === 'number') {
		// 临时覆盖：直接使用传入的 LLM 配置
		await extractDynamicInfoWithLlm(opts.llm_config_id)
	} else {
		await extractDynamicInfo()
	}
})

async function onApplyContext(ctx: string) {
	try {
		contextTemplate.value = ctx || ''
		await cardStore.modifyCard(localCard.id, { ai_context_template: contextTemplate.value } as any, { skipHooks: true })
		ElMessage.success('上下文模板已保存到卡片')
	} catch {
		ElMessage.error('保存上下文失败')
	}
}

// 根据当前编辑态内容与项目卡片，自动提取参与者
function extractParticipantsForCurrentChapter(): string[] {
	try {
		// 改为直接从 Chapter 模型的 entity_list 读取
		const list = (localCard.content as any)?.entity_list
		if (Array.isArray(list)) {
			return list.map((x:any) => typeof x === 'string' ? x : (x?.name || '')).filter((s:string) => !!s).slice(0, 6)
		}
	} catch {}
	return []
}

function openReferenceSelector(payload?: string) {
	// 确保抽屉中的最新模板同步到本地
	if (typeof payload === 'string') {
		contextTemplate.value = payload
	}
	openSelector.value = true
}

function handleSelectorConfirm(snippet: string) {
	// 按抽屉 textarea 的光标位置插入（不写入正文）
	try {
		const textarea = document.querySelector('.context-area textarea') as HTMLTextAreaElement | null
		if (textarea) {
			const start = textarea.selectionStart ?? contextTemplate.value.length
			const end = textarea.selectionEnd ?? start
			const before = (contextTemplate.value || '').slice(0, start)
			const after = (contextTemplate.value || '').slice(end)
			const next = `${before}${snippet}${after}`
			contextTemplate.value = next
			// 将内容也写回到抽屉输入框，保持所见即所得
			textarea.value = next
			// 触发 v-model 同步
			textarea.dispatchEvent(new Event('input', { bubbles: true }))
			// 将光标移到插入片段后
			const caret = start + snippet.length
			requestAnimationFrame(() => textarea.setSelectionRange(caret, caret))
			return
		}
	} catch {}
	// 回退：找不到 textarea 时，末尾追加
	contextTemplate.value = contextTemplate.value ? contextTemplate.value + snippet : snippet
}

function handleDrawerInput(ev: Event) {
	const textarea = ev.target as HTMLTextAreaElement
	// 同步抽屉内文本到本地模板，避免选择器插入时丢失前缀
	contextTemplate.value = textarea.value
	// 不再把 @ 插入到正文或做位置记录
}

// 外部卡片变更
watch(() => props.card, (newCard) => {
	Object.assign(localCard, newCard)
	const newContent = (newCard.content as any)?.content || '<p></p>'
	if (editor.value && editor.value.getHTML() !== newContent) {
		editor.value.commands.setContent(newContent)
	}
}, { deep: true })

// 编辑器内容变化同步
watch(() => editor.value?.getJSON(), () => {
	if (editor.value) {
		wordCount.value = editor.value.getText().length
		localCard.content = {
			...(localCard.content || {}),
			// 将编辑器纯文本保存到 Chapter.content（字符串）
			content: editor.value.getText(),
			word_count: wordCount.value,
			volume_number: (props.contextParams as any)?.volume_number ?? (localCard.content as any)?.volume_number,
			chapter_number: (props.contextParams as any)?.chapter_number ?? (localCard.content as any)?.chapter_number,
			title: (localCard.content as any)?.title ?? localCard.title,
		}
		// 若父组件托管章节模型，向父级同步
		if (props.chapter) {
			emit('update:chapter', {
				title: (localCard.content as any)?.title ?? localCard.title,
				volume_number: (localCard.content as any)?.volume_number,
				chapter_number: (localCard.content as any)?.chapter_number,
				entity_list: (localCard.content as any)?.entity_list || [],
				content: (localCard.content as any)?.content || ''
			})
		}
	}
})

function handleKeydown(event: KeyboardEvent) {
	if (autoIndent.value && event.key === 'Enter') {
		setTimeout(() => {
			if (autoIndent.value && editor.value) {
				editor.value.commands.insertContent('　　')
			}
		}, 10)
	}
}

function toggleAutoIndent() {
	autoIndent.value = !autoIndent.value
	ElMessage.info(`自动缩进已${autoIndent.value ? '开启' : '关闭'}`)
}

async function handleSave() {
	// 父组件托管时，仅触发保存事件
	if (props.chapter) {
		emit('save')
		return
	}
	const updatePayload: CardUpdate = {
		title: localCard.title,
		content: {
			...localCard.content,
			// 保存为 Chapter 模型：正文用纯文本
			content: editor.value?.getText() || '',
			word_count: wordCount.value,
			volume_number: (props.contextParams as any)?.volume_number ?? (localCard.content as any)?.volume_number,
			chapter_number: (props.contextParams as any)?.chapter_number ?? (localCard.content as any)?.chapter_number,
		}
	}
	await cardStore.modifyCard(localCard.id, updatePayload)
	// 触发策略：按“每窗口N章”累计命中再触发（此处仅记录命中，具体动作可在独立任务中处理）
	try {
		const projectId = projectStore.currentProject?.id || (localCard as any).project_id
		const win = consistencySettings.settings.kg_trigger.on_chapter_window_close.window_size
		const enabled = consistencySettings.settings.kg_enabled && consistencySettings.settings.kg_trigger.on_chapter_window_close.enabled
		if (enabled && projectId) {
			const hit = consistencyRuntime.onChapterSaved(projectId, localCard.id, win)
			if (hit) {
				// 命中窗口边界：此处预留后续触发（如通知、队列、提示）
				// ElMessage.info(`已累计 ${win} 章，建议在空闲时触发知识一致性构建`)
			}
		}
	} catch {}
}

function resolveLlmConfigId(): number | undefined {
	const selectedParamCard = aiParamCardStore.findByKey?.(selectedAiParamCardId.value)
	if (selectedParamCard?.llm_config_id) return selectedParamCard.llm_config_id
	// 回退：尝试使用第一个参数卡
	const first = (aiParamCardStore as any).paramCards?.[0]
	return first?.llm_config_id
}

function resolvePromptName(): string | undefined {
	const selectedParamCard = aiParamCardStore.findByKey?.(selectedAiParamCardId.value)
	if (selectedParamCard?.prompt_name) return selectedParamCard.prompt_name
	const first = (aiParamCardStore as any).paramCards?.[0]
	return first?.prompt_name
}

function resolveSampling() {
	const selectedParamCard = aiParamCardStore.findByKey?.(selectedAiParamCardId.value)
	const first = (aiParamCardStore as any).paramCards?.[0]
	const src: any = selectedParamCard || first || {}
	return { temperature: src.temperature, max_tokens: src.max_tokens, timeout: src.timeout }
}

async function executeAIContinuation() {
	if (!editor.value) return
	const llmConfigId = resolveLlmConfigId()
	if (!llmConfigId) {
		ElMessage.error('请先选择一个有效的AI参数配置（模型）')
		return
	}
	const promptName = resolvePromptName()
	if (!promptName) {
		ElMessage.error('所选参数卡未配置提示词（prompt），请先在参数卡中设置 prompt_name')
		return
	}
	aiLoading.value = true

	// 1) 先装配上下文：前端统一拼装，再透传给后端（后端仅回退时装配）
	let currentContextBlock = ''
	try {
		const projectId = projectStore.currentProject?.id || (localCard as any).project_id
		const vol = (localCard as any)?.content?.volume_number ?? (props.contextParams as any)?.volume_number
		const ch = (localCard as any)?.content?.chapter_number ?? (props.contextParams as any)?.chapter_number
		const parts = extractParticipantsForCurrentChapter()
		const ctx = await assembleContext({ project_id: projectId, volume_number: vol, chapter_number: ch, participants: parts, current_draft_tail: '' })
		// 将结构化 facts 格式化为文本块
		function fmtFacts(): string {
			try {
				const fs: any = ctx.facts_structured || {}
				const lines: string[] = []
				if (Array.isArray(fs.fact_summaries) && fs.fact_summaries.length) {
					lines.push('关键事实:')
					for (const s of fs.fact_summaries) lines.push(`- ${s}`)
				}
				if (Array.isArray(fs.relation_summaries) && fs.relation_summaries.length) {
					lines.push('关系摘要:')
					for (const r of fs.relation_summaries) {
						lines.push(`- ${r.a} ↔ ${r.b}（${r.kind}）`)
						if (r.a_to_b_addressing || r.b_to_a_addressing) {
							const a1 = r.a_to_b_addressing ? `A称B：${r.a_to_b_addressing}` : ''
							const b1 = r.b_to_a_addressing ? `B称A：${r.b_to_a_addressing}` : ''
							if (a1 || b1) lines.push(`  · ${[a1, b1].filter(Boolean).join(' ｜ ')}`)
						}
						if (Array.isArray(r.recent_dialogues) && r.recent_dialogues.length) {
							lines.push('  · 对话样例:')
							for (const d of r.recent_dialogues) lines.push(`    - ${d}`)
						}
						if (Array.isArray(r.recent_event_summaries) && r.recent_event_summaries.length) {
							lines.push('  · 近期事件:')
							for (const ev of r.recent_event_summaries) {
								const tag = [ev?.volume_number != null ? `卷${ev.volume_number}` : null, ev?.chapter_number != null ? `章${ev.chapter_number}` : null].filter(Boolean).join(' ')
								lines.push(`    - ${ev.summary}${tag ? `（${tag}）` : ''}`)
							}
						}
					}
				}
				return lines.join('\n')
			} catch { return '' }
		}
		const factsText = fmtFacts()
		currentContextBlock = factsText ? `【事实子图】\n${factsText}` : (ctx.facts_subgraph ? `【事实子图】\n${ctx.facts_subgraph}` : '')
	} catch {}

	// 2) 合并“上下文抽屉模板解析”的文本（若有）
	let templateBlock = ''
	try {
		const currentCardForResolve = { ...props.card, content: localCard.content }
		const resolved = resolveTemplate({ template: contextTemplate.value || '', cards: cards.value, currentCard: currentCardForResolve as any })
		templateBlock = (resolved || '').trim()
	} catch { templateBlock = contextTemplate.value || '' }

	const mergedContext = [templateBlock,currentContextBlock].filter(Boolean).join('\n\n')

	const requestData: ContinuationRequest = {
		previous_content: editor.value.getText(),
		llm_config_id: llmConfigId,
		stream: true,
		prompt_name: promptName,
		// 将前端装配的上下文整体传给后端
		current_draft_tail: mergedContext,
		// 透传上下文边界与参与者（后端会基于这些装配上下文注入）
		...(props.contextParams || {}) as any,
	} as any

	// 采样与配额（若参数卡有配置则一并透传）
	try {
		const { temperature, max_tokens, timeout } = resolveSampling()
		if (typeof temperature === 'number') (requestData as any).temperature = temperature
		if (typeof max_tokens === 'number') (requestData as any).max_tokens = max_tokens
		if (typeof timeout === 'number') (requestData as any).timeout = timeout
	} catch {}

	// 自动注入参与者（同卷同章的章节大纲卡片 character_list）
	try {
		const autoParticipants = extractParticipantsForCurrentChapter()
		if (autoParticipants.length) (requestData as any).participants = autoParticipants
	} catch {}

	editor.value.commands.focus('end')

	let accumulated = ''

	streamHandle = generateContinuationStreaming(
		requestData,
		(chunk) => {
			if (!chunk) return
			// 增量插入：若服务端返回的是“累计内容”，仅写入新增部分
			let delta = chunk
			if (accumulated && chunk.startsWith(accumulated)) {
				delta = chunk.slice(accumulated.length)
			}
			if (delta) {
				// 规范换行：
				// 1) 折叠 >=3 的换行为 2 个
				// 2) 将“单个换行”视为同段内的空格，避免每行一个字
				const normalized = String(delta)
					.replace(/\r/g, '')
					// 将连续换行统一折叠为单个换行，避免过度空白或断行
					.replace(/\n+/g, '\n')
				// 始终在文末插入，避免光标位置影响
				editor.value?.commands.focus('end')
				editor.value?.commands.insertContent(normalized)
				try {
					const container = document.querySelector('.editor-content') as HTMLElement | null
					if (container) {
						requestAnimationFrame(() => { container.scrollTop = container.scrollHeight })
					}
				} catch {}
			}
			if (chunk.length > accumulated.length) accumulated = chunk
		},
		() => {
			aiLoading.value = false
			streamHandle = null
			// 生成完成后做一次自动缩进应用（将每段首插入全角空格）
			try {
				if (autoIndent.value && editor.value) {
					const text = editor.value.getText() || ''
					const adjusted = text
						.split('\n')
						.map(line => line.trim().length ? (line.startsWith('　　') ? line : `　　${line}`) : '')
						.join('\n')
					editor.value.commands.setContent(`<p>${adjusted.split('\n').map(l => l || '<br>').join('</p><p>')}</p>`, { emitUpdate: true })
				}
			} catch {}
			ElMessage.success('AI续写完成！')
		},
		(error) => {
			aiLoading.value = false
			streamHandle = null
			console.error('AI续写失败:', error)
			ElMessage.error('AI续写失败')
		}
	)
}

function interruptStream() {
	try { streamHandle?.cancel(); } catch {}
}

async function extractDynamicInfo() {
	if (!editor.value) return
	const llmConfigId = resolveLlmConfigId()
	if (!llmConfigId) {
		ElMessage.error('请先选择一个有效的AI参数配置（模型）')
		return
	}
	await extractDynamicInfoWithLlm(llmConfigId)
}

async function extractDynamicInfoWithLlm(llmConfigId: number) {
	if (!editor.value) return
	try {
		const projectId = projectStore.currentProject?.id || (localCard as any).project_id
		if (!projectId) {
			ElMessage.error('未找到当前项目ID')
			return
		}
		// 自动参与者
		let participants = extractParticipantsForCurrentChapter()
		// 章节正文文本
		const chapterText = editor.value.getText() || ''
		// 当前阶段概述（沿用上下文解析逻辑：从抽屉模板或上下文参数中拿到）
		let stageOverview = ''
		try {
			// 优先从上下文参数
			if ((props.contextParams as any)?.stage_overview) {
				stageOverview = String((props.contextParams as any).stage_overview || '')
			}
			// 兜底：若抽屉模板包含 @stage:current.overview 则解析其文本
			if (!stageOverview && contextTemplate.value?.includes('@stage:current.overview')) {
				const currentCardForResolve = { ...props.card, content: editor.value?.getJSON() || '' }
				const resolved = resolveTemplate({ template: 'current_stage_overview: @stage:current.overview', cards: cards.value, currentCard: currentCardForResolve as any })
				const line = (resolved || '').split('\n').find(l => l.startsWith('current_stage_overview:')) || ''
				stageOverview = line.replace('current_stage_overview:', '').trim()
			}
		} catch {}

		const extraContext = (props.contextParams as any)?.extra_context_fn()

		if (previewBeforeUpdate.value) {
			// 仅提取并预览
			const data = await extractDynamicInfoOnly({ project_id: projectId, text: chapterText, participants, llm_config_id: llmConfigId, extra_context: extraContext })
			previewData.value = data
			previewDialogVisible.value = true
		} else {
			// 直接提取并更新（已移除旧的组合端点，改为预览+确认流程）
			const payload: UpdateDynamicInfoOutput = await extractDynamicInfoOnly({ project_id: projectId, text: chapterText, participants, llm_config_id: llmConfigId, extra_context: extraContext })
			const resp = await updateDynamicInfoOnly({ project_id: projectId, data: payload as any, queue_size: 5 })
			if (resp?.success) {
				ElMessage.success(`动态信息已更新：${resp.updated_card_count} 个角色卡`)
			} else {
				ElMessage.warning('未检测到需要更新的动态信息')
			}
		}
	} catch (e) {
		console.error(e)
		ElMessage.error('提取动态信息失败')
	}
}

async function confirmApplyUpdates() {
	try {
		const projectId = projectStore.currentProject?.id || (localCard as any).project_id
		if (!projectId || !previewData.value) { previewDialogVisible.value = false; return }
		// 收集 modify_info_list（仅提交用户改动的权重）
		const modify: any[] = []
		try {
			for (const role of (previewData.value.info_list || [])) {
				const name = role.name
				const di: any = role.dynamic_info || {}
				for (const catKey of Object.keys(di)) {
					const items = di[catKey] || []
					for (const it of items) {
						if (typeof it.weight === 'number' && it.id && it.id > 0) {
							// 直接提交，后端会按 id 替换为新权重
							modify.push({ name, dynamic_type: catKey, id: it.id, weight: it.weight })
						}
					}
				}
			}
		} catch {}

		const payload: any = { ...previewData.value }
		if (modify.length) payload.modify_info_list = modify

		const resp = await updateDynamicInfoOnly({ project_id: projectId, data: payload as any, queue_size: 5 })
		if (resp?.success) {
			ElMessage.success(`动态信息已更新：${resp.updated_card_count} 个角色卡`)
			// 刷新卡片数据，确保主界面展示最新结果
			try { await cardStore.fetchCards(projectId) } catch {}
		} else {
			ElMessage.warning('未检测到需要更新的动态信息')
		}
	} catch (e) {
		console.error(e)
		ElMessage.error('更新动态信息失败')
	} finally {
		previewDialogVisible.value = false
		previewData.value = null
	}
}

async function handleIngestRelations() {
	if (!editor.value) return
	const llmConfigId = resolveLlmConfigId()
	if (!llmConfigId) { ElMessage.error('请先选择一个有效的AI参数配置（模型）'); return }
	try {
		const text = editor.value.getText() || ''
		const participants = extractParticipantsForCurrentChapter()
		const vol = (localCard as any)?.content?.volume_number ?? (props.contextParams as any)?.volume_number
		const ch = (localCard as any)?.content?.chapter_number ?? (props.contextParams as any)?.chapter_number
		const data = await extractRelationsOnly({ text, participants, llm_config_id: llmConfigId, volume_number: vol, chapter_number: ch })
		relationsPreview.value = data
		relationsPreviewVisible.value = true
	} catch (e) {
		console.error(e)
		ElMessage.error('关系抽取失败')
	}
}

async function confirmIngestRelationsFromPreview() {
	try {
		const projectId = projectStore.currentProject?.id || (localCard as any).project_id
		if (!projectId || !relationsPreview.value) { relationsPreviewVisible.value = false; return }
		const vol = (localCard as any)?.content?.volume_number ?? (props.contextParams as any)?.volume_number
		const ch = (localCard as any)?.content?.chapter_number ?? (props.contextParams as any)?.chapter_number
		const resp = await ingestRelationsFromPreview({ project_id: projectId, data: relationsPreview.value, volume_number: vol, chapter_number: ch })
		ElMessage.success(`已写入关系/别名：${resp.written} 条`)
	} catch (e) {
		console.error(e)
		ElMessage.error('关系入图失败')
	} finally {
		relationsPreviewVisible.value = false
		relationsPreview.value = null
	}
}

function removePreviewItem(roleName: string, catKey: string, index: number) {
	if (!previewData.value) return
	const role = previewData.value.info_list.find(r => r.name === roleName)
	if (role) {
		const catItems = role.dynamic_info[catKey] || []
		if (catItems.length > index) {
			catItems.splice(index, 1)
			if (catItems.length === 0) {
				delete role.dynamic_info[catKey]
				if (Object.keys(role.dynamic_info).length === 0) {
					delete role.dynamic_info
				}
			}
		}
	}
}

onUnmounted(() => {
	editor.value?.destroy()
	editorStore.setApplyChapterReplacements(null)
	try { streamHandle?.cancel(); } catch {}
})

// 将卷号/章节号/标题注入到全局 editorStore，方便 OutlinePanel 使用
try {
	const title = props.card?.title || ''
	const vol = Number((props.contextParams as any)?.volume_number ?? (props.card as any)?.content?.volume_number ?? NaN)
	const ch = Number((props.contextParams as any)?.chapter_number ?? (props.card as any)?.content?.chapter_number ?? NaN)
	editorStore.setCurrentContextInfo({ title, volume: Number.isNaN(vol) ? null : vol, chapter: Number.isNaN(ch) ? null : ch })
} catch {}
</script>

<style scoped>
/* 保持与原样式一致 */
.editor-container {
	border: 1px solid var(--el-border-color);
	border-radius: var(--el-border-radius-base);
	display: flex;
	flex-direction: column;
	height: 100%;
}

.toolbar {
	padding: 8px;
	border-bottom: 1px solid var(--el-border-color);
	background-color: var(--el-fill-color-lighter);
	display: flex;
	align-items: center;
	flex-wrap: wrap;
	gap: 8px;
}
.mx-2 {
	margin-left: 0.5rem;
	margin-right: 0.5rem;
}
.ml-2 {
	margin-left: 0.5rem;
}
.flex-spacer {
	flex-grow: 1;
}
.word-count-display {
	font-size: 14px;
	color: var(--el-text-color-regular);
	margin-right: 12px;
}

.editor-content-wrapper {
	flex-grow: 1;
	display: flex;
	flex-direction: column;
	overflow: hidden;
}
.chapter-title-display {
	padding: 20px 20px 10px 20px;
	border-bottom: 1px solid var(--el-border-color-light);
	background-color: var(--el-fill-color-lighter);
}
.chapter-title-wrapper {
	display: flex;
	align-items: center;
	justify-content: center;
	position: relative;
}
.chapter-title-text {
	margin: 0;
	font-size: 24px;
	font-weight: bold;
}
/* 右侧空白处的操作区 */
.title-actions {
	position: absolute;
	right: 20px;
	top: 50%;
	transform: translateY(-50%);
	display: flex;
	align-items: center;
	gap: 8px;
}
.param-select-top { width: 220px; }

.editor-content {
	flex-grow: 1;
	overflow-y: auto;
	background-color: var(--el-bg-color);
}
.editor-content :deep(.ProseMirror) {
	padding: 20px;
	min-height: 100%;
	outline: none;
	line-height: 1.8;
	color: var(--el-text-color-primary);
	background-color: transparent;
}
.role-block { margin-bottom: 16px; }
.cat-title { font-weight: 600; margin: 8px 0; }
.preview-block {
	background: var(--el-fill-color-light);
	padding: 12px;
	border-radius: 6px;
	max-height: 60vh;
	overflow: auto;
}
</style> 