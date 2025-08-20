<template>
	<div class="editor-container">
		<div class="toolbar">
			<el-button-group class="mx-2">
				<el-tooltip content="自动缩进" placement="bottom">
					<el-button :type="autoIndent ? 'primary' : ''" @click="toggleAutoIndent">缩进</el-button>
				</el-tooltip>

				<!-- 新增字号与行距下拉菜单 -->
				<el-dropdown @command="(c:any) => fontSize = c" trigger="click">
					<el-button>
						字号 <el-icon class="el-icon--right"><arrow-down /></el-icon>
					</el-button>
					<template #dropdown>
						<el-dropdown-menu>
							<el-dropdown-item :command="14" :class="{ 'is-active': fontSize === 14 }">14px</el-dropdown-item>
							<el-dropdown-item :command="16" :class="{ 'is-active': fontSize === 16 }">16px</el-dropdown-item>
							<el-dropdown-item :command="18" :class="{ 'is-active': fontSize === 18 }">18px</el-dropdown-item>
							<el-dropdown-item :command="20" :class="{ 'is-active': fontSize === 20 }">20px</el-dropdown-item>
						</el-dropdown-menu>
					</template>
				</el-dropdown>

				<el-dropdown @command="(c:any) => lineHeight = c" trigger="click">
					<el-button>
						行距 <el-icon class="el-icon--right"><arrow-down /></el-icon>
					</el-button>
					<template #dropdown>
						<el-dropdown-menu>
							<el-dropdown-item :command="1.4" :class="{ 'is-active': lineHeight === 1.4 }">1.4</el-dropdown-item>
							<el-dropdown-item :command="1.6" :class="{ 'is-active': lineHeight === 1.6 }">1.6</el-dropdown-item>
							<el-dropdown-item :command="1.8" :class="{ 'is-active': lineHeight === 1.8 }">1.8</el-dropdown-item>
							<el-dropdown-item :command="2.0" :class="{ 'is-active': lineHeight === 2.0 }">2.0</el-dropdown-item>
							<el-dropdown-item :command="2.2" :class="{ 'is-active': lineHeight === 2.2 }">2.2</el-dropdown-item>
						</el-dropdown-menu>
					</template>
				</el-dropdown>
			</el-button-group>

			<div class="flex-spacer"></div>

			<span class="word-count-display">{{ wordCount }} 字</span>

			<el-input-number v-model="fontSize" :min="12" :max="28" :step="1" size="small" controls-position="right" style="width: 110px; margin-right: 8px; display: none;" />
			<el-input-number v-model="lineHeight" :min="1.2" :max="2.4" :step="0.1" size="small" controls-position="right" style="width: 120px; margin-right: 12px; display: none;" />

			<el-popover placement="bottom-end" title="AI续写设置" :width="400" trigger="click">
				<!-- 预留更多设置项 -->
			</el-popover>

			<el-button @click="openDrawer = true" plain>上下文注入</el-button>
			<el-button @click="executeAIContinuation" type="primary" :loading="aiLoading">
				AI生成
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
					<div class="title-actions">
						<el-select v-model="selectedAiParamCardId" placeholder="选择参数卡" class="param-select-top" @change="onParamChange" filterable>
							<el-option v-for="p in paramCards" :key="p.id" :label="p.name || ('参数卡 ' + p.id)" :value="p.id" />
						</el-select>
					</div>
				</div>
			</div>

			<!-- CodeMirror 容器 -->
			<div ref="cmRoot" class="editor-content"></div>
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
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { storeToRefs } from 'pinia'
import { useCardStore } from '@renderer/stores/useCardStore'
import { useProjectStore } from '@renderer/stores/useProjectStore'
import { useAIParamCardStore } from '@renderer/stores/useAIParamCardStore'
import { useEditorStore } from '@renderer/stores/useEditorStore'
import type { CardRead, CardUpdate } from '@renderer/api/cards'
import { generateContinuationStreaming, type ContinuationRequest } from '@renderer/api/ai'
import { resolveTemplate } from '@renderer/services/contextResolver'
import { extractDynamicInfoOnly, updateDynamicInfoOnly, type UpdateDynamicInfoOutput, extractRelationsOnly, ingestRelationsFromPreview, type RelationExtractionOutput } from '@renderer/api/memory'
import { ArrowDown } from '@element-plus/icons-vue'
import ContextDrawer from '../common/ContextDrawer.vue'
import CardReferenceSelectorDialog from '../cards/CardReferenceSelectorDialog.vue'

import { EditorState } from '@codemirror/state'
import { EditorView, keymap } from '@codemirror/view'
import { defaultKeymap, history, historyKeymap, insertNewline } from '@codemirror/commands'

const props = defineProps<{ card: CardRead; chapter?: any; prefetched?: any | null; contextParams?: { project_id?: number; volume_number?: number; chapter_number?: number; participants?: string[]; extra_context_fn?: Function } }>()
const emit = defineEmits<{ (e: 'update:chapter', value: any): void; (e: 'save'): void }>()

const cardStore = useCardStore()
const projectStore = useProjectStore()
const aiParamCardStore = useAIParamCardStore()
const editorStore = useEditorStore()
const { cards } = storeToRefs(cardStore)
const { paramCards } = storeToRefs(aiParamCardStore)

const ready = ref(false)
const cmRoot = ref<HTMLElement | null>(null)
let view: EditorView | null = null

const selectedAiParamCardId = ref<string | undefined>(props.card.selected_ai_param_card_id ?? undefined)
watch(() => props.card.selected_ai_param_card_id, (id) => { selectedAiParamCardId.value = id ?? undefined })

function onParamChange() {
	cardStore.modifyCard(localCard.id, { selected_ai_param_card_id: selectedAiParamCardId.value } as any, { skipHooks: true })
}

const localCard = reactive({
	...props.card,
	content: {
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

watch(() => props.chapter, (ch) => {
	if (!ch) return
	const c: any = ch
	const text = typeof c.content === 'string' ? c.content : (localCard.content as any)?.content || ''
	localCard.content = {
		...(localCard.content || {}),
		content: text,
		word_count: typeof c.content === 'string' ? c.content.length : (localCard.content as any)?.word_count || 0,
		volume_number: c.volume_number ?? (localCard.content as any)?.volume_number,
		chapter_number: c.chapter_number ?? (localCard.content as any)?.chapter_number,
		title: c.title ?? (localCard.content as any)?.title ?? props.card.title,
		entity_list: Array.isArray(c.entity_list) ? c.entity_list : ((localCard.content as any)?.entity_list || []),
	}
	if (view && getText() !== text) setText(text)
}, { deep: true })

function computeWordCount(text: string): number {
	return (text || '').replace(/\s+/g, '').length
}

const wordCount = ref(0)
const autoIndent = ref(false)
const aiLoading = ref(false)
let streamHandle: { cancel: () => void } | null = null
const openDrawer = ref(false)
const editorText = computed(() => getText())
const contextTemplate = ref('')
watch(() => props.card, (c) => { if (c && (c as any).ai_context_template != null) contextTemplate.value = String((c as any).ai_context_template || '') }, { immediate: true })
const openSelector = ref(false)
const previewBeforeUpdate = ref(true)
const previewDialogVisible = ref(false)
const previewData = ref<UpdateDynamicInfoOutput | null>(null)
const relationsPreviewVisible = ref(false)
const relationsPreview = ref<RelationExtractionOutput | null>(null)

// 字号/行距（默认 16px / 1.8）
const fontSize = ref<number>(16)
const lineHeight = ref<number>(1.8)
const fontSizePx = computed(() => `${fontSize.value}px`)
const lineHeightStr = computed(() => String(lineHeight.value))

function formatCategory(catKey: any) { return String(catKey) }

function setText(text: string) {
	if (!view) return
	view.dispatch({
		changes: { from: 0, to: view.state.doc.length, insert: text || '' }
	})
}

function getText(): string {
	return view ? view.state.doc.toString() : ''
}

function appendAtEnd(delta: string) {
	if (!view || !delta) return
	const end = view.state.doc.length
	view.dispatch({
		changes: { from: end, to: end, insert: delta },
		// 滚动到文档末尾
		effects: EditorView.scrollIntoView(end, { y: "end" })
	})
	// 滚动到底
	try {
		const scroller = (cmRoot.value?.querySelector('.cm-scroller') as HTMLElement) || cmRoot.value
		if (scroller) requestAnimationFrame(() => { scroller.scrollTop = scroller.scrollHeight })
	} catch {}
}

function indentNonEmptyLines(text: string): string {
	return (text || '')
		.split('\n')
		.map(line => {
			const raw = line
			const trimmed = raw.trim()
			if (!trimmed) return ''
			return raw.startsWith('　　') ? raw : `　　${raw}`
		})
		.join('\n')
}

function initEditor() {
	if (!cmRoot.value) return
	const initialText = String((localCard.content as any)?.content || '')
	
	const customKeymap = [
		{
			key: 'Enter',
			run: (v: EditorView) => {
				// 先执行默认的换行
				insertNewline(v)
				// 如果开启了自动缩进，则在换行后插入缩进符
				if (autoIndent.value) {
					const { from, to } = v.state.selection.main
					v.dispatch({ changes: { from, to, insert: '　　' } })
				}
				return true
			}
		},
		{
			key: 'Mod-s', // Ctrl+S or Cmd+S
			run: (v: EditorView) => {
				handleSave()
				return true
			},
			preventDefault: true
		}
	]

	view = new EditorView({
		parent: cmRoot.value,
		state: EditorState.create({
			doc: initialText,
			extensions: [
				history(),
				keymap.of([...customKeymap, ...defaultKeymap, ...historyKeymap]),
				EditorView.lineWrapping,
				EditorView.updateListener.of((update) => {
					if (!update.docChanged) return
					const txt = update.state.doc.toString()
					wordCount.value = computeWordCount(txt)
					localCard.content = {
						...(localCard.content || {}),
						content: txt,
						word_count: wordCount.value,
						volume_number: (props.contextParams as any)?.volume_number ?? (localCard.content as any)?.volume_number,
						chapter_number: (props.contextParams as any)?.chapter_number ?? (localCard.content as any)?.chapter_number,
						title: (localCard.content as any)?.title ?? localCard.title,
					}
					if (props.chapter) {
						emit('update:chapter', {
							title: (localCard.content as any)?.title ?? localCard.title,
							volume_number: (localCard.content as any)?.volume_number,
							chapter_number: (localCard.content as any)?.chapter_number,
							entity_list: (localCard.content as any)?.entity_list || [],
							content: (localCard.content as any)?.content || ''
						})
					}
				})
			]
		})
	})
	// 初始化字数
	wordCount.value = computeWordCount(getText())
	ready.value = true
}

function toggleAutoIndent() {
	autoIndent.value = !autoIndent.value
	ElMessage.info(`自动缩进已${autoIndent.value ? '开启' : '关闭'}`)

	// 开启时，检查并缩进当前段落
	if (autoIndent.value && view) {
		const { state } = view
		const { from, to } = state.selection.main
		// 获取当前行
		const line = state.doc.lineAt(from)
		const lineContent = line.text.trim()

		if (lineContent && !line.text.startsWith('　　')) {
			view.dispatch({
				changes: { from: line.from, insert: '　　' }
			})
		}
	}
}

async function handleSave() {
	if (props.chapter) { emit('save'); return }
	const updatePayload: CardUpdate = {
		title: localCard.title,
		content: {
			...localCard.content,
			content: getText(),
			word_count: wordCount.value,
			volume_number: (props.contextParams as any)?.volume_number ?? (localCard.content as any)?.volume_number,
			chapter_number: (props.contextParams as any)?.chapter_number ?? (localCard.content as any)?.chapter_number,
		}
	}
	await cardStore.modifyCard(localCard.id, updatePayload)
}

function resolveLlmConfigId(): number | undefined {
	const selectedParamCard = aiParamCardStore.findByKey?.(selectedAiParamCardId.value)
	if (selectedParamCard?.llm_config_id) return selectedParamCard.llm_config_id
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

function formatFactsFromContext(ctx: any | null | undefined): string {
	try {
		if (!ctx) return ''
		const factsStruct: any = (ctx as any)?.facts_structured || {}
		const lines: string[] = []
		if (Array.isArray(factsStruct.fact_summaries) && factsStruct.fact_summaries.length) {
			lines.push('关键事实:')
			for (const s of factsStruct.fact_summaries) lines.push(`- ${s}`)
		}
		if (Array.isArray(factsStruct.relation_summaries) && factsStruct.relation_summaries.length) {
			lines.push('关系摘要:')
			for (const r of factsStruct.relation_summaries) {
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
		const text = lines.join('\n')
		if (text) return text
		const subgraph = (ctx as any)?.facts_subgraph
		return subgraph ? String(subgraph) : ''
	} catch { return '' }
}

async function executeAIContinuation() {
	const llmConfigId = resolveLlmConfigId()
	if (!llmConfigId) { ElMessage.error('请先选择一个有效的AI参数配置（模型）'); return }
	const promptName = resolvePromptName()
	if (!promptName) { ElMessage.error('所选参数卡未配置提示词（prompt）'); return }

	aiLoading.value = true

	let currentContextBlock = ''
	try {
		const factsText = formatFactsFromContext(props.prefetched)
		currentContextBlock = factsText ? `【事实子图】\n${factsText}` : ''
	} catch {}

	let templateBlock = ''
	try {
		const currentCardForResolve = { ...props.card, content: localCard.content }
		const resolved = resolveTemplate({ template: contextTemplate.value || '', cards: cards.value, currentCard: currentCardForResolve as any })
		templateBlock = (resolved || '').trim()
	} catch { templateBlock = contextTemplate.value || '' }

	const mergedContext = [templateBlock,currentContextBlock].filter(Boolean).join('\n\n')

	const requestData: ContinuationRequest = {
		previous_content: getText(),
		llm_config_id: llmConfigId,
		stream: true,
		prompt_name: promptName,
		current_draft_tail: mergedContext,
		...(props.contextParams || {}) as any,
	} as any

	try {
		const { temperature, max_tokens, timeout } = resolveSampling()
		if (typeof temperature === 'number') (requestData as any).temperature = temperature
		if (typeof max_tokens === 'number') (requestData as any).max_tokens = max_tokens
		if (typeof timeout === 'number') (requestData as any).timeout = timeout
	} catch {}

	try {
		const autoParticipants = extractParticipantsForCurrentChapter()
		if (autoParticipants.length) (requestData as any).participants = autoParticipants
	} catch {}

	if (view) { view.focus(); const end = view.state.doc.length; view.dispatch({ selection: { anchor: end } }) }

	let accumulated = ''

	streamHandle = generateContinuationStreaming(
		requestData,
		(chunk) => {
			if (!chunk) return
			let delta = chunk
			if (accumulated && chunk.startsWith(accumulated)) {
				delta = chunk.slice(accumulated.length)
			}
			if (delta) {
				const normalized = String(delta)
					.replace(/\r/g, '')
					.replace(/\n+/g, m => (m.length === 2 ? '\n' : m))
				appendAtEnd(normalized)
			}
			if (chunk.length > accumulated.length) accumulated = chunk
		},
		() => {
			aiLoading.value = false
			streamHandle = null
			try {
				let text = getText() || ''
				// 压缩恰好两个换行为一个，>=3 不动
				text = text.replace(/\n+/g, m => (m.length === 2 ? '\n' : m))
				if (autoIndent.value) text = indentNonEmptyLines(text)
				setText(text)
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

function extractParticipantsForCurrentChapter(): string[] {
	try {
		const list = (localCard.content as any)?.entity_list
		if (Array.isArray(list)) {
			return list.map((x:any) => typeof x === 'string' ? x : (x?.name || '')).filter((s:string) => !!s).slice(0, 6)
		}
	} catch {}
	return []
}

function extractParticipantsWithTypeForCurrentChapter(): { name: string, type: string }[] {
	const result: { name: string, type: string }[] = []
	try {
		const entityList = (localCard.content as any)?.entity_list
		if (!Array.isArray(entityList)) return []

		const allCards = cards.value || []
		const cardMap = new Map(allCards.map(c => [c.title, c]))

		for (const item of entityList) {
			const name = (typeof item === 'string' ? item : item?.name)?.trim()
			if (!name) continue

			let type = 'unknown'
			if (typeof item !== 'string' && item.entity_type) {
				type = item.entity_type
			} else if (cardMap.has(name)) {
				const card = cardMap.get(name)
				// 简单的从卡片类型名推断实体类型
				const cardTypeName = card?.card_type?.name || ''
				if (cardTypeName.includes('角色')) type = 'character'
				else if (cardTypeName.includes('组织')) type = 'organization'
				else if (cardTypeName.includes('场景')) type = 'scene'
				else if (cardTypeName.includes('物品')) type = 'item'
				else if (cardTypeName.includes('概念')) type = 'concept'
			}
			result.push({ name, type })
		}
	} catch (e) {
		console.error("Failed to extract participants with type:", e)
	}
	return result.slice(0, 10) // 适当放宽数量限制
}

function extractCharacterParticipantsForCurrentChapter(): string[] {
	try {
		const list = (localCard.content as any)?.entity_list
		const result: string[] = []
		const characterNames = new Set<string>((cards.value || [])
			.filter((c:any) => c?.card_type?.name === '角色卡')
			.map((c:any) => (c?.title || '').trim())
			.filter((s:string) => !!s))
		if (Array.isArray(list)) {
			for (const item of list) {
				if (typeof item === 'string') {
					const nm = (item || '').trim()
					if (nm && characterNames.has(nm)) result.push(nm)
				} else if (item && typeof item === 'object') {
					const nm = (item.name || '').trim()
					const t = (item.entity_type || '').trim()
					if (nm && (t === 'character' || characterNames.has(nm))) result.push(nm)
				}
			}
		}
		return Array.from(new Set(result)).slice(0, 6)
	} catch {}
	return []
}

async function onApplyContext(ctx: string) {
	try {
		contextTemplate.value = ctx || ''
		await cardStore.modifyCard(localCard.id, { ai_context_template: contextTemplate.value } as any, { skipHooks: true })
		ElMessage.success('上下文模板已保存到卡片')
	} catch {
		ElMessage.error('保存上下文失败')
	}
}

function openReferenceSelector(payload?: string) {
	if (typeof payload === 'string') contextTemplate.value = payload
	openSelector.value = true
}

function handleSelectorConfirm(snippet: string) {
	try {
		const textarea = document.querySelector('.context-area textarea') as HTMLTextAreaElement | null
		if (textarea) {
			const start = textarea.selectionStart ?? contextTemplate.value.length
			const end = textarea.selectionEnd ?? start
			const before = (contextTemplate.value || '').slice(0, start)
			const after = (contextTemplate.value || '').slice(end)
			const next = `${before}${snippet}${after}`
			contextTemplate.value = next
			textarea.value = next
			textarea.dispatchEvent(new Event('input', { bubbles: true }))
			const caret = start + snippet.length
			requestAnimationFrame(() => textarea.setSelectionRange(caret, caret))
			return
		}
	} catch {}
	contextTemplate.value = contextTemplate.value ? contextTemplate.value + snippet : snippet
}

// 触发“动态信息提取”（右栏调用）
editorStore.setTriggerExtractDynamicInfo(async (opts) => {
	if (typeof opts?.preview === 'boolean') previewBeforeUpdate.value = !!opts.preview
	if (typeof opts?.llm_config_id === 'number') {
		await extractDynamicInfoWithLlm(opts.llm_config_id)
	} else {
		await extractDynamicInfo()
	}
})

// 跨组件替换
editorStore.setApplyChapterReplacements(async (pairs) => {
	if (!view) return
	let original = getText() || ''
	let replaced = original
	for (const { from, to } of (pairs || [])) {
		if (!from) continue
		const safeFrom = String(from).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
		replaced = replaced.replace(new RegExp(safeFrom, 'g'), String(to ?? ''))
	}
	setText(replaced)
})

async function extractDynamicInfo() {
	const llmConfigId = resolveLlmConfigId()
	if (!llmConfigId) { ElMessage.error('请先选择一个有效的AI参数配置（模型）'); return }
	await extractDynamicInfoWithLlm(llmConfigId)
}

async function extractDynamicInfoWithLlm(llmConfigId: number) {
	try {
		const projectId = projectStore.currentProject?.id || (localCard as any).project_id
		if (!projectId) { ElMessage.error('未找到当前项目ID'); return }
		// 修正：调用 extractParticipantsWithTypeForCurrentChapter
		let participants = extractParticipantsWithTypeForCurrentChapter()
		const chapterText = getText() || ''
		let stageOverview = ''
		try {
			if ((props.contextParams as any)?.stage_overview) {
				stageOverview = String((props.contextParams as any).stage_overview || '')
			}
			if (!stageOverview && contextTemplate.value?.includes('@stage:current.overview')) {
				const currentCardForResolve = { ...props.card, content: chapterText }
				const resolved = resolveTemplate({ template: 'current_stage_overview: @stage:current.overview', cards: cards.value, currentCard: currentCardForResolve as any })
				const line = (resolved || '').split('\n').find(l => l.startsWith('current_stage_overview:')) || ''
				stageOverview = line.replace('current_stage_overview:', '').trim()
			}
		} catch {}
		const extraContext = (props.contextParams as any)?.extra_context_fn()
		if (previewBeforeUpdate.value) {
			// 仅提取并预览
			const data = await extractDynamicInfoOnly({ project_id: projectId, text: chapterText, participants, llm_config_id: llmConfigId, extra_context: extraContext } as any)
			previewData.value = data
			previewDialogVisible.value = true
		} else {
			// 直接提取并更新（已移除旧的组合端点，改为预览+确认流程）
			const payload: UpdateDynamicInfoOutput = await extractDynamicInfoOnly({ project_id: projectId, text: chapterText, participants, llm_config_id: llmConfigId, extra_context: extraContext } as any)
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
		const modify: any[] = []
		try {
			for (const role of (previewData.value.info_list || [])) {
				const name = role.name
				const di: any = role.dynamic_info || {}
				for (const catKey of Object.keys(di)) {
					const items = di[catKey] || []
					for (const it of items) {
						if (typeof it.weight === 'number' && it.id && it.id > 0) {
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
	const llmConfigId = resolveLlmConfigId()
	if (!llmConfigId) { ElMessage.error('请先选择一个有效的AI参数配置（模型）'); return }
	try {
		const text = getText() || ''
		const participants = extractParticipantsWithTypeForCurrentChapter()
		const vol = (localCard as any)?.content?.volume_number ?? (props.contextParams as any)?.volume_number
		const ch = (localCard as any)?.content?.chapter_number ?? (props.contextParams as any)?.chapter_number

		let mergedText = text
		try {
			const factsText = formatFactsFromContext(props.prefetched)
			if (factsText) mergedText = `【已知事实子图】\n${factsText}\n\n正文如下：\n${text}`
		} catch {}

		const data = await extractRelationsOnly({ text: mergedText, participants, llm_config_id: llmConfigId, volume_number: vol, chapter_number: ch } as any)
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
		const di: Record<string, any[]> = (role as any).dynamic_info || {}
		const catItems = di[catKey] || []
		if (catItems.length > index) {
			catItems.splice(index, 1)
			if (catItems.length === 0) {
				delete di[catKey]
				if (Object.keys(di).length === 0) {
					delete (role as any).dynamic_info
				}
			}
			(role as any).dynamic_info = di
		}
	}
}

onMounted(() => {
	initEditor()
	try {
		const title = props.card?.title || ''
		const vol = Number((props.contextParams as any)?.volume_number ?? (props.card as any)?.content?.volume_number ?? NaN)
		const ch = Number((props.contextParams as any)?.chapter_number ?? (props.card as any)?.content?.chapter_number ?? NaN)
		editorStore.setCurrentContextInfo({ title, volume: Number.isNaN(vol) ? null : vol, chapter: Number.isNaN(ch) ? null : ch })
	} catch {}
})

onUnmounted(() => {
	try { view?.destroy() } catch {}
	editorStore.setApplyChapterReplacements(null)
	try { streamHandle?.cancel(); } catch {}
})
</script>

<style scoped>
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
/* 使下拉按钮与缩进按钮组风格更统一 */
.toolbar .el-dropdown {
	margin-left: -1px;
}
.toolbar .el-dropdown .el-button {
	border-top-left-radius: 0;
	border-bottom-left-radius: 0;
}
:deep(.el-dropdown-menu__item.is-active) {
	color: var(--el-color-primary);
	font-weight: bold;
}
.mx-2 { margin-left: 0.5rem; margin-right: 0.5rem; }
.ml-2 { margin-left: 0.5rem; }
.flex-spacer { flex-grow: 1; }
.word-count-display { font-size: 14px; color: var(--el-text-color-regular); margin-right: 12px; }

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
	/* 修正：容器本身不滚动，交由 CodeMirror 内部处理 */
	overflow: hidden;
	background-color: var(--el-bg-color);
}

/* CodeMirror 内部样式 */
.editor-content :deep(.cm-editor) {
	/* 修正：高度占满容器，而不是无限增长 */
	height: 100%;
	outline: none;
	line-height: 1.8;
	color: var(--el-text-color-primary);
	background-color: transparent;
}
.editor-content :deep(.cm-content) {
	padding: 20px;
	color: #303133;
	font-size: v-bind(fontSizePx);
	line-height: v-bind(lineHeightStr);
}

/* 取消高亮行背景，保证纯文本阅读观感 */
.editor-content :deep(.cm-activeLine) {
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