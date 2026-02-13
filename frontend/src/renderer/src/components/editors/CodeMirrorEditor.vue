<template>
	<div class="chapter-studio">
	<div class="toolbar">
		<div class="toolbar-row">
			<!-- 编辑功能组 -->
			<div class="toolbar-group">
				<span class="group-label">编辑</span>
				<el-dropdown @command="(c:any) => fontSize = c" size="small">
					<el-button size="small">
						{{ fontSize }}px
						<el-icon class="el-icon--right"><arrow-down /></el-icon>
					</el-button>
					<template #dropdown>
						<el-dropdown-menu>
							<el-dropdown-item :command="14">小 (14px)</el-dropdown-item>
							<el-dropdown-item :command="16">中 (16px)</el-dropdown-item>
							<el-dropdown-item :command="18">大 (18px)</el-dropdown-item>
							<el-dropdown-item :command="20">特大 (20px)</el-dropdown-item>
						</el-dropdown-menu>
					</template>
				</el-dropdown>
				
				<el-dropdown @command="(c:any) => lineHeight = c" size="small">
					<el-button size="small">
						{{ lineHeight }}
						<el-icon class="el-icon--right"><arrow-down /></el-icon>
					</el-button>
					<template #dropdown>
						<el-dropdown-menu>
							<el-dropdown-item :command="1.4">紧凑</el-dropdown-item>
							<el-dropdown-item :command="1.6">适中</el-dropdown-item>
							<el-dropdown-item :command="1.8">舒适</el-dropdown-item>
							<el-dropdown-item :command="2.0">宽松</el-dropdown-item>
						</el-dropdown-menu>
					</template>
				</el-dropdown>
			</div>

			<div class="toolbar-divider"></div>
			
			<!-- AI功能组 -->
			<div class="toolbar-group">
				<span class="group-label">AI</span>
				<el-button type="primary" size="small" :loading="aiLoading" @click="executeAIContinuation">
					<el-icon><MagicStick /></el-icon> 续写
				</el-button>
				
				<el-button-group size="small">
					<el-button plain :loading="aiLoading" @click="executePolish">
						<el-icon><Document /></el-icon> 润色
					</el-button>
					<el-dropdown @command="handlePolishPromptChange" trigger="click">
						<el-button plain :loading="aiLoading">
							<el-icon><ArrowDown /></el-icon>
						</el-button>
						<template #dropdown>
							<el-dropdown-menu>
								<el-dropdown-item 
									v-for="p in polishPrompts" 
									:key="p" 
									:command="p"
									:class="{ 'is-selected': p === currentPolishPrompt }"
								>
									<div class="prompt-item">
										<span>{{ p }}</span>
										<el-icon v-if="p === currentPolishPrompt" class="check-icon"><Select /></el-icon>
									</div>
								</el-dropdown-item>
							</el-dropdown-menu>
						</template>
					</el-dropdown>
				</el-button-group>
				
				<el-button-group size="small">
					<el-button plain :loading="aiLoading" @click="executeExpand">
						<el-icon><MagicStick /></el-icon> 扩写
					</el-button>
					<el-dropdown @command="handleExpandPromptChange" trigger="click">
						<el-button plain :loading="aiLoading">
							<el-icon><ArrowDown /></el-icon>
						</el-button>
						<template #dropdown>
							<el-dropdown-menu>
								<el-dropdown-item 
									v-for="p in expandPrompts" 
									:key="p" 
									:command="p"
									:class="{ 'is-selected': p === currentExpandPrompt }"
								>
									<div class="prompt-item">
										<span>{{ p }}</span>
										<el-icon v-if="p === currentExpandPrompt" class="check-icon"><Select /></el-icon>
									</div>
								</el-dropdown-item>
							</el-dropdown-menu>
						</template>
					</el-dropdown>
				</el-button-group>
				
				<el-button type="danger" plain size="small" :disabled="!streamHandle" @click="interruptStream">
					<el-icon><CircleClose /></el-icon> 中断
				</el-button>
				
				<!-- AI模型配置 -->
				<AIPerCardParams :card-id="props.card.id" :card-type-name="props.card.card_type?.name" />
			</div>
		</div>
	</div>

	<div class="editor-content-wrapper">
		<!-- 简化的标题区域 -->
	<div class="chapter-header">
		<div class="title-section">
			<h1 
				class="chapter-title" 
				contenteditable="true"
				@blur="handleTitleBlur"
				@keydown.enter.prevent="handleTitleEnter"
				ref="titleElement"
			>{{ localCard.title }}</h1>
			<div class="title-meta">
				<el-icon class="word-count-icon"><Timer /></el-icon>
				<span class="word-count-text">{{ wordCount }} 字</span>
			</div>
		</div>
	</div>

		<!-- CodeMirror 容器 -->
		<div ref="cmRoot" class="editor-content"></div>
	</div>

		<!-- 右键快速编辑菜单 -->
		<Teleport to="body">
			<div 
				v-if="contextMenu.visible" 
				class="context-menu-popup"
				:style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
			>
				<div v-if="!contextMenu.expanded" class="context-menu-compact">
					<el-button 
						type="primary" 
						size="small" 
						@click="expandContextMenu"
					>
						快速编辑
					</el-button>
				</div>
				<div v-else class="context-menu-expanded">
					<el-input
						v-model="contextMenu.userRequirement"
						:autosize="{ minRows: 2, maxRows: 4 }"
						type="textarea"
						placeholder="描述你的要求，如：让语气更加强硬、增加环境描写..."
						size="small"
						style="margin-bottom: 8px;"
					/>
					<div class="context-menu-actions">
						<el-button 
							type="primary" 
							size="small" 
							:loading="aiLoading"
							@click="handleContextMenuPolish"
						>
							<el-icon><Document /></el-icon> 润色
						</el-button>
						<el-button 
							type="primary" 
							size="small"
							:loading="aiLoading"
							@click="handleContextMenuExpand"
						>
							<el-icon><MagicStick /></el-icon> 扩写
						</el-button>
						<el-button 
							size="small"
							@click="closeContextMenu"
						>
							取消
						</el-button>
					</div>
				</div>
			</div>
		</Teleport>

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
										<span v-if="row.recent_event_summaries[row.recent_event_summaries.length-1].volume_number != null || row.recent_event_summaries[row.recent_event_summaries.length-1].chapter_number != null" class="event-meta">
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
import { ref, reactive, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { storeToRefs } from 'pinia'
import { useCardStore } from '@renderer/stores/useCardStore'
import { useProjectStore } from '@renderer/stores/useProjectStore'
import { usePerCardAISettingsStore, type PerCardAIParams } from '@renderer/stores/usePerCardAISettingsStore'
import { useEditorStore } from '@renderer/stores/useEditorStore'
import type { CardRead, CardUpdate } from '@renderer/api/cards'
import { generateContinuationStreaming, type ContinuationRequest, getAIConfigOptions, type AIConfigOptions } from '@renderer/api/ai'
import { getCardAIParams, updateCardAIParams, applyCardAIParamsToType } from '@renderer/api/setting'
import { extractDynamicInfoOnly, updateDynamicInfoOnly, type UpdateDynamicInfoOutput, extractRelationsOnly, ingestRelationsFromPreview, type RelationExtractionOutput } from '@renderer/api/memory'
import { ArrowDown, Document, MagicStick, CircleClose, Connection, List, Timer, Select } from '@element-plus/icons-vue'
import AIPerCardParams from '../common/AIPerCardParams.vue'
import { resolveTemplate } from '@renderer/services/contextResolver'

import { EditorState, StateEffect, StateField } from '@codemirror/state'
import { EditorView, keymap, Decoration, DecorationSet } from '@codemirror/view'
import { defaultKeymap, history, historyKeymap, insertNewline } from '@codemirror/commands'

const props = defineProps<{ card: CardRead; chapter?: any; prefetched?: any | null; contextParams?: { project_id?: number; volume_number?: number; chapter_number?: number; participants?: string[]; extra_context_fn?: Function } }>()
const emit = defineEmits<{ 
	(e: 'update:chapter', value: any): void
	(e: 'save'): void
	(e: 'switch-tab', tab: string): void
	(e: 'update:dirty', value: boolean): void
}>()

const cardStore = useCardStore()
const projectStore = useProjectStore()
const perCardStore = usePerCardAISettingsStore()
const editorStore = useEditorStore()
const { cards } = storeToRefs(cardStore)

const ready = ref(false)
const cmRoot = ref<HTMLElement | null>(null)
const titleElement = ref<HTMLElement | null>(null)
let view: EditorView | null = null

// 自定义高亮系统
const setHighlightEffect = StateEffect.define<{ from: number; to: number } | null>()

const highlightField = StateField.define<DecorationSet>({
	create() {
		return Decoration.none
	},
	update(highlights, tr) {
		highlights = highlights.map(tr.changes)
		for (const effect of tr.effects) {
			if (effect.is(setHighlightEffect)) {
				if (effect.value === null) {
					highlights = Decoration.none
				} else {
					const decoration = Decoration.mark({
						class: 'cm-ai-highlight'
					}).range(effect.value.from, effect.value.to)
					highlights = Decoration.set([decoration])
				}
			}
		}
		return highlights
	},
	provide: f => EditorView.decorations.from(f)
})

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

// 每卡片参数
const editingParams = ref<PerCardAIParams>({})
const aiOptions = ref<AIConfigOptions | null>(null)
async function loadAIOptions() { try { aiOptions.value = await getAIConfigOptions() } catch {} }
const perCardParams = computed(() => perCardStore.getByCardId(props.card.id))
const selectedModelName = computed(() => {
	try {
		const id = (perCardParams.value || editingParams.value)?.llm_config_id
		const list = aiOptions.value?.llm_configs || []
		const found = list.find(m => m.id === id)
		return found?.display_name || (id != null ? String(id) : '')
	} catch { return '' }
})
const paramSummary = computed(() => {
	const p = perCardParams.value || editingParams.value
	const model = selectedModelName.value ? `模型:${selectedModelName.value}` : '模型:未设'
	const prompt = p?.prompt_name ? `任务:${p.prompt_name}` : '任务:未设'
	const t = p?.temperature != null ? `温度:${p.temperature}` : ''
	const m = p?.max_tokens != null ? `max_tokens:${p.max_tokens}` : ''
	return [model, prompt, t, m].filter(Boolean).join(' · ')
})

watch(() => props.card, async (newCard) => {
	if (!newCard) return
	await loadAIOptions()
	// 优先读取后端"有效参数"（类型默认或实例覆盖）
	try {
		const resp = await getCardAIParams(newCard.id)
		const eff = (resp as any)?.effective_params
		if (eff && Object.keys(eff).length) {
			editingParams.value = { ...eff }
			perCardStore.setForCard(newCard.id, { ...eff })
			return
		}
	} catch {}
	// 回退：使用本地存储或预设
	const saved = perCardStore.getByCardId(newCard.id)
	if (saved) editingParams.value = { ...saved }
	else {
		const preset = getPresetForType(newCard.card_type?.name) || {}
		if (!preset.llm_config_id) { const first = aiOptions.value?.llm_configs?.[0]; if (first) preset.llm_config_id = first.id }
		editingParams.value = { ...preset }
		perCardStore.setForCard(newCard.id, editingParams.value)
	}
}, { immediate: true })

// 监听卡片内容变化（如灵感助手修改后），同步到编辑器
watch(() => props.card?.content, (newContent) => {
	if (!newContent || !view) return
	
	try {
		const newText = typeof (newContent as any)?.content === 'string' 
			? (newContent as any).content 
			: ''
		const currentText = getText()
		
		// 只有当内容真的不同，且不是由当前编辑器触发的保存时，才更新
		// （通过比较 originalContent 判断：如果相同说明是外部修改）
		if (newText !== currentText && newText !== originalContent.value) {
			console.log('🔄 [CodeMirror] 检测到外部内容更新，同步到编辑器')
			
			// 更新编辑器内容
			setText(newText)
			
			// 更新 localCard
			localCard.content = {
				...(localCard.content || {}),
				...(newContent as any),
				content: newText,
				word_count: newText.length
			}
			
			// 更新原始内容引用（避免触发 dirty）
			originalContent.value = newText
			isDirty.value = false
			emit('update:dirty', false)
			
			// 更新字数
			wordCount.value = computeWordCount(newText)
			
			console.log('✅ [CodeMirror] 编辑器内容已同步')
		}
	} catch (e) {
		console.error('❌ [CodeMirror] 同步内容失败:', e)
	}
}, { deep: true })

function applyAndSavePerCardParams() {
	try { perCardStore.setForCard(props.card.id, { ...editingParams.value }); ElMessage.success('已保存到本卡片设置') } catch { ElMessage.error('保存失败') }
}
function resetToPreset() {
	const preset = getPresetForType(props.card.card_type?.name)
	editingParams.value = { ...(preset || {}) }
	perCardStore.setForCard(props.card.id, editingParams.value)
}
function getPresetForType(typeName?: string) : PerCardAIParams | undefined {
	const map: Record<string, PerCardAIParams> = {
		'章节大纲': { prompt_name: '章节大纲', llm_config_id: 1, temperature: 0.6, max_tokens: 4096, timeout: 60 },
		'内容生成': { prompt_name: '内容生成', llm_config_id: 1, temperature: 0.7, max_tokens: 8192, timeout: 60 },
	}
	return map[typeName || '']
}

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
const aiLoading = ref(false)
let streamHandle: { cancel: () => void } | null = null
const previewBeforeUpdate = ref(true)

// 章节正文：保存时是否自动触发提取（角色动态信息 / 关系入图）
const AUTO_EXTRACT_DYNAMIC_KEY = 'nf:chapter:auto_extract_dynamic_on_save'
const AUTO_EXTRACT_RELATIONS_KEY = 'nf:chapter:auto_extract_relations_on_save'

function isDynamicAutoExtractEnabled(): boolean {
	try {
		return localStorage.getItem(AUTO_EXTRACT_DYNAMIC_KEY) === '1'
	} catch {
		return false
	}
}

function isRelationsAutoExtractEnabled(): boolean {
	try {
		return localStorage.getItem(AUTO_EXTRACT_RELATIONS_KEY) === '1'
	} catch {
		return false
	}
}

// 右键菜单状态
const contextMenu = reactive({
	visible: false,
	expanded: false,
	x: 0,
	y: 0,
	userRequirement: '',
	selectedText: null as { text: string; from: number; to: number } | null
})

// 高亮管理
const currentHighlight = ref<{ from: number; to: number } | null>(null)

// 设置高亮
function setHighlight(from: number, to: number) {
	if (!view) return
	// CodeMirror 不允许空范围的 decoration
	if (from >= to) {
		console.log('⚠️ [Highlight] 跳过空范围高亮:', { from, to })
		return
	}
	currentHighlight.value = { from, to }
	view.dispatch({
		effects: setHighlightEffect.of({ from, to })
	})
	console.log('✨ [Highlight] 设置高亮:', { from, to })
}

// 清除高亮
function clearHighlight() {
	if (!view) return
	currentHighlight.value = null
	view.dispatch({
		effects: setHighlightEffect.of(null)
	})
	console.log('🧹 [Highlight] 清除高亮')
}

// 更新高亮范围（用于 AI 输出时）
function updateHighlight(from: number, to: number) {
	if (!view) return
	// CodeMirror 不允许空范围的 decoration
	if (from >= to) {
		return
	}
	currentHighlight.value = { from, to }
	view.dispatch({
		effects: setHighlightEffect.of({ from, to })
	})
}

// 跟踪原始内容以检测dirty状态
const originalContent = ref<string>('')
const isDirty = ref(false)
const previewDialogVisible = ref(false)
const previewData = ref<UpdateDynamicInfoOutput | null>(null)
const relationsPreviewVisible = ref(false)
const relationsPreview = ref<RelationExtractionOutput | null>(null)

// 字号/行距（默认 16px / 1.8）
const fontSize = ref<number>(16)
const lineHeight = ref<number>(1.8)

// 润色和扩写的提示词列表
const polishPrompts = ref<string[]>([])
const expandPrompts = ref<string[]>([])
const currentPolishPrompt = ref('润色')
const currentExpandPrompt = ref('扩写')
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

function getSelectedText(): { text: string; from: number; to: number } | null {
	if (!view) return null
	const { from, to } = view.state.selection.main
	if (from === to) return null // 没有选中内容
	return {
		text: view.state.doc.sliceString(from, to),
		from,
		to
	}
}

function replaceSelectedText(newText: string) {
	if (!view) return
	const { from, to } = view.state.selection.main
	view.dispatch({
		changes: { from, to, insert: newText },
		selection: { anchor: from + newText.length }
	})
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


function initEditor() {
	if (!cmRoot.value) return
	const initialText = String((localCard.content as any)?.content || '')
	
	// 保存原始内容
	originalContent.value = initialText
	isDirty.value = false
	emit('update:dirty', false)
	
	const customKeymap = [
		{
			key: 'Enter',
			run: (v: EditorView) => {
				// 执行默认的换行
				insertNewline(v)
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
				highlightField,
				// 关键：限制编辑器高度由父容器决定，而不是根据内容自动扩展
				EditorView.theme({
					"&": { height: "100%" },
					".cm-scroller": { overflow: "auto" }
				}),
				// 点击编辑器时清除高亮
				EditorView.domEventHandlers({
					mousedown: (e, view) => {
						if (currentHighlight.value) {
							clearHighlight()
							return false
						}
						return false
					}
				}),
				EditorView.updateListener.of((update) => {
					if (!update.docChanged) return
					const txt = update.state.doc.toString()
					wordCount.value = computeWordCount(txt)
					
					// 检测dirty状态
					const newDirty = txt !== originalContent.value
					if (newDirty !== isDirty.value) {
						isDirty.value = newDirty
						emit('update:dirty', newDirty)
					}
					
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
	
	// 添加右键菜单监听器到 CodeMirror 的 DOM 元素
	if (view && cmRoot.value) {
		const editorDom = cmRoot.value.querySelector('.cm-editor') as HTMLElement
		if (editorDom) {
			editorDom.addEventListener('contextmenu', handleEditorContextMenu)
			console.log('✅ [ContextMenu] 右键菜单监听器已添加')
		} else {
			console.warn('⚠️ [ContextMenu] 未找到 .cm-editor 元素')
		}
	}
}


// 加载可用提示词列表
async function loadPrompts() {
	try {
		const options = await getAIConfigOptions()
		const allPrompts = options?.prompts || []
		
		// 获取所有提示词名称
		const allPromptNames = allPrompts.map(p => p.name)
		
		// 润色和扩写都使用所有可用提示词
		polishPrompts.value = allPromptNames.length > 0 ? allPromptNames : ['润色']
		expandPrompts.value = allPromptNames.length > 0 ? allPromptNames : ['扩写']
		
		// 设置默认选中的提示词
		if (allPromptNames.includes('润色')) {
			currentPolishPrompt.value = '润色'
		} else if (allPromptNames.length > 0) {
			currentPolishPrompt.value = allPromptNames[0]
		}
		
		if (allPromptNames.includes('扩写')) {
			currentExpandPrompt.value = '扩写'
		} else if (allPromptNames.length > 0) {
			currentExpandPrompt.value = allPromptNames[0]
		}
	} catch (e) {
		console.error('Failed to load prompts:', e)
		polishPrompts.value = ['润色']
		expandPrompts.value = ['扩写']
	}
}


// 处理标题编辑（正文页大标题）
async function handleTitleBlur() {
	if (!titleElement.value) return
	const newTitle = titleElement.value.textContent?.trim() || ''
	if (newTitle && newTitle !== localCard.title) {
		await saveTitle(newTitle)
	} else {
		// 恢复原标题
		if (titleElement.value) titleElement.value.textContent = localCard.title
	}
}

async function handleTitleEnter() {
	if (!titleElement.value) return
	titleElement.value.blur() // 触发 blur 事件统一保存
}

// 保存标题：同时更新 card.title 与 content.title，保证上下文使用的 @self.content.title 为最新
async function saveTitle(newTitle: string) {
	try {
		const trimmed = newTitle.trim()
		if (!trimmed) return
		localCard.title = trimmed
		localCard.content = {
			...(localCard.content || {}),
			// 仅更新 title 字段，正文内容等保持不变
			...(localCard.content as any),
			title: trimmed,
		}
		const updatePayload: CardUpdate = {
			title: trimmed,
			content: localCard.content as any,
		}
		await cardStore.modifyCard(localCard.id, updatePayload)
		ElMessage.success('标题已更新')
	} catch (e) {
		ElMessage.error('标题更新失败')
		// 恢复原标题
		if (titleElement.value) titleElement.value.textContent = localCard.title
	}
}

// 保存正文：可选接收来自父级的最新标题，一次性写入 card.title 与 content.title
async function handleSave(newTitle?: string) {
	if (props.chapter) { emit('save'); return }
	const effectiveTitle = (typeof newTitle === 'string' && newTitle.trim()) ? newTitle.trim() : localCard.title
	if (effectiveTitle && effectiveTitle !== localCard.title) {
		localCard.title = effectiveTitle
	}
	const nextContent = {
		...localCard.content,
		content: getText(),
		word_count: wordCount.value,
		volume_number: (props.contextParams as any)?.volume_number ?? (localCard.content as any)?.volume_number,
		chapter_number: (props.contextParams as any)?.chapter_number ?? (localCard.content as any)?.chapter_number,
		// 始终把最新标题写入 content.title，供上下文模板和筛选使用
		title: effectiveTitle || (localCard.content as any)?.title || localCard.title,
	}
	const updatePayload: CardUpdate = {
		title: effectiveTitle,
		content: nextContent as any,
		needs_confirmation: false,  // 清除 AI 修改标记，触发工作流
	}
	localCard.content = nextContent as any
	await cardStore.modifyCard(localCard.id, updatePayload)
		
	// 保存成功后重置dirty状态
	originalContent.value = getText()
	isDirty.value = false
	emit('update:dirty', false)

	// 若当前卡片为章节正文，且开启了“保存时自动提取”，则在保存成功后自动触发提取
	try {
		const typeName = (props.card as any)?.card_type?.name || ''
		const needDynamic = isDynamicAutoExtractEnabled()
		const needRelations = isRelationsAutoExtractEnabled()
		if (typeName === '章节正文' && (needDynamic || needRelations)) {
			const llmConfigId = resolveLlmConfigId()
			if (llmConfigId) {
				if (needDynamic) {
					await extractDynamicInfoWithLlm(llmConfigId)
				}
				if (needRelations) {
					await extractRelationsWithLlm(llmConfigId)
				}
			} else if (needDynamic || needRelations) {
				ElMessage.warning('未找到章节对应的AI参数配置，自动提取已跳过，请在右侧手动执行提取')
			}
		}
	} catch (e) {
		console.error('自动提取失败:', e)
		ElMessage.error('自动提取失败，请在右侧手动点击重试')
	}
		
	// 返回保存的内容供历史版本使用
	return updatePayload.content
}

function resolveLlmConfigId(): number | undefined {
	const p = perCardParams.value || editingParams.value
	return p?.llm_config_id
}

function resolvePromptName(): string | undefined {
	const p = perCardParams.value || editingParams.value
	return p?.prompt_name
}

function resolveSampling() {
	const src: any = perCardParams.value || editingParams.value || {}
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
	if (!llmConfigId) { ElMessage.error('请先设置有效的模型ID'); return }
	const promptName = resolvePromptName()
	if (!promptName) { ElMessage.error('未设置生成任务名（prompt）'); return }

	aiLoading.value = true

	// 1. 解析卡片的 ai_context_template（上下文注入的引用内容）
	let resolvedContextTemplate = ''
	try {
		const aiContextTemplate = (props.card as any)?.ai_context_template || ''
		if (aiContextTemplate) {
			const currentCardWithContent = { 
				...props.card, 
				content: {
					...localCard.content,
					content: getText()
				}
			}
			resolvedContextTemplate = resolveTemplate({ 
				template: aiContextTemplate, 
				cards: cards.value, 
				currentCard: currentCardWithContent as any 
			})
		}
	} catch (e) {
		console.error('Failed to resolve ai_context_template:', e)
	}

	// 2. 格式化事实子图（参与实体）
	let factsText = ''
	try {
		factsText = formatFactsFromContext(props.prefetched)
	} catch {}

	// 3. 组合完整的上下文信息
	const contextParts: string[] = []
	if (resolvedContextTemplate) {
		contextParts.push(`【引用上下文】\n${resolvedContextTemplate}`)
	}
	if (factsText) {
		contextParts.push(`【事实子图】\n${factsText}`)
	}
	const contextInfoBlock = contextParts.join('\n\n')

	// 4. 计算已有内容字数
	const existingText = getText()
	const existingWordCount = computeWordCount(existingText)

	const requestData: ContinuationRequest = {
		previous_content: existingText,
		context_info: contextInfoBlock,
		existing_word_count: existingWordCount,
		llm_config_id: llmConfigId,
		stream: true,
		prompt_name: promptName,
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

	executeAIGeneration(requestData, false, '续写')
}

function handlePolishPromptChange(promptName: string) {
	currentPolishPrompt.value = promptName
	ElMessage.success(`已切换润色提示词为: ${promptName}`)
}

function handleExpandPromptChange(promptName: string) {
	currentExpandPrompt.value = promptName
	ElMessage.success(`已切换扩写提示词为: ${promptName}`)
}

async function executePolish() {
	await executeAIEdit(currentPolishPrompt.value)
}

async function executeExpand() {
	await executeAIEdit(currentExpandPrompt.value)
}

// 右键菜单处理函数
function handleEditorContextMenu(e: MouseEvent) {
	console.log(' [ContextMenu] 右键事件触发')
	
	// 检查是否有选中文本
	const selection = getSelectedText()
	if (!selection || !selection.text.trim()) {
		console.log('⚠️ [ContextMenu] 没有选中文本，使用默认菜单')
		return // 没有选中文本，使用默认右键菜单
	}
	
	
	e.preventDefault()
	e.stopPropagation()
	
	// 保存选中的文本信息
	contextMenu.selectedText = selection
	contextMenu.visible = true
	contextMenu.expanded = false
	contextMenu.userRequirement = ''
	
	// 设置自定义高亮，替代默认选中效果
	setHighlight(selection.from, selection.to)
	
	// 计算菜单位置（避免超出屏幕）
	const menuWidth = 280
	const menuHeight = 200
	let x = e.clientX
	let y = e.clientY
	
	if (x + menuWidth > window.innerWidth) {
		x = window.innerWidth - menuWidth - 10
	}
	if (y + menuHeight > window.innerHeight) {
		y = window.innerHeight - menuHeight - 10
	}
	
	contextMenu.x = x
	contextMenu.y = y
	
	
	// 延迟注册点击外部关闭的监听器，避免立即触发
	setTimeout(() => {
		if (!contextMenuClickListenerAdded) {
			window.addEventListener('click', handleClickOutside, { capture: true })
			contextMenuClickListenerAdded = true
		}
	}, 100)
}

let contextMenuClickListenerAdded = false

function expandContextMenu() {
	contextMenu.expanded = true
	// 自动聚焦输入框
	nextTick(() => {
		const input = document.querySelector('.context-menu-popup textarea') as HTMLTextAreaElement
		if (input) {
			input.focus()
		} else {
			console.warn('⚠️ [ContextMenu] 未找到输入框')
		}
	})
}

function closeContextMenu() {
	contextMenu.visible = false
	contextMenu.expanded = false
	contextMenu.userRequirement = ''
	contextMenu.selectedText = null
	
	// 移除点击外部关闭的监听器
	if (contextMenuClickListenerAdded) {
		window.removeEventListener('click', handleClickOutside, { capture: true })
		contextMenuClickListenerAdded = false
	}
}

async function handleContextMenuPolish() {
	const requirement = contextMenu.userRequirement.trim()
	closeContextMenu()
	await executeAIEdit(currentPolishPrompt.value, requirement || undefined)
}

async function handleContextMenuExpand() {
	const requirement = contextMenu.userRequirement.trim()
	closeContextMenu()
	await executeAIEdit(currentExpandPrompt.value, requirement || undefined)
}

async function executeAIEdit(promptName: string, userRequirement?: string) {
	const selectedText = getSelectedText()
	if (!selectedText) {
		ElMessage.warning(`请先选中要${promptName}的内容`)
		return
	}

	const llmConfigId = resolveLlmConfigId()
	if (!llmConfigId) { 
		ElMessage.error('请先设置有效的模型ID')
		return 
	}

	aiLoading.value = true

	// 获取完整文本
	const fullText = getText()

	// 1. 解析 ai_context_template（引用上下文）
	let resolvedContextTemplate = ''
	try {
		const aiContextTemplate = (props.card as any)?.ai_context_template || ''
		if (aiContextTemplate) {
			const currentCardWithContent = { 
				...props.card, 
				content: {
					...localCard.content,
					content: fullText
				}
			}
			resolvedContextTemplate = resolveTemplate({ 
				template: aiContextTemplate, 
				cards: cards.value, 
				currentCard: currentCardWithContent as any 
			})
		}
	} catch (e) {
		console.error('Failed to resolve ai_context_template:', e)
	}

	// 2. 格式化事实子图（参与实体）
	let factsText = ''
	try {
		factsText = formatFactsFromContext(props.prefetched)
	} catch {}

	// 3. 组合上下文信息：引用上下文 + 事实子图 + 用户要求 + 上文 + 选中内容 + 下文
	const contextParts: string[] = []
	if (resolvedContextTemplate) {
		contextParts.push(`【引用上下文】\n${resolvedContextTemplate}`)
	}
	if (factsText) {
		contextParts.push(`【事实子图】\n${factsText}`)
	}
	if (userRequirement) {
		contextParts.push(`【用户要求】\n${userRequirement}`)
	}
	
	// 提取上文（选中内容之前）
	const beforeText = fullText.substring(0, selectedText.from)
	if (beforeText.trim()) {
		// 截取最后1000字作为上文
		const truncatedBefore = beforeText.length > 1000 ? '...' + beforeText.slice(-1000) : beforeText
		contextParts.push(`【上文】\n${truncatedBefore}`)
	}
	
	// 选中的内容
	contextParts.push(`【需要${promptName}的内容】\n${selectedText.text}`)
	
	// 提取下文（选中内容之后）
	const afterText = fullText.substring(selectedText.to)
	if (afterText.trim()) {
		// 截取前500字作为下文
		const truncatedAfter = afterText.length > 500 ? afterText.slice(0, 500) + '...' : afterText
		contextParts.push(`【下文】\n${truncatedAfter}`)
	}
	const contextInfoBlock = contextParts.join('\n\n')

	const requestData: ContinuationRequest = {
		previous_content: '', // 润色/扩写时为空，所有上下文都在 context_info 中
		context_info: contextInfoBlock,
		llm_config_id: llmConfigId,
		stream: true,
		prompt_name: promptName,
		append_continuous_novel_directive: false, // 润色/扩写不需要"连续输出"指令
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

	executeAIGeneration(requestData, true, promptName, selectedText.from, selectedText.to)
}

function executeAIGeneration(
	requestData: ContinuationRequest, 
	replaceMode = false, 
	taskName = 'AI生成',
	replaceFrom?: number,
	replaceTo?: number
) {
	let accumulated = ''
	let isFirstChunk = true
	let outputStartPos = replaceFrom ?? 0
	let currentOutputLength = 0

	if (view) { 
		view.focus()
		if (!replaceMode) {
			// 续写模式：光标移到末尾
			const end = view.state.doc.length
			view.dispatch({ selection: { anchor: end } })
			outputStartPos = end
		} else if (replaceFrom !== undefined && replaceTo !== undefined) {
			// 替换模式：先清空选中内容
			view.dispatch({
				changes: { from: replaceFrom, to: replaceTo, insert: '' },
				selection: { anchor: replaceFrom }
			})
			outputStartPos = replaceFrom
			// 不设置高亮，等第一个字符输出时再设置（避免空范围错误）
		}
	}

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
				
				if (replaceMode) {
					// 替换模式：追加到当前光标位置（已清空选中内容）
					if (view) {
						const pos = view.state.selection.main.head
						view.dispatch({
							changes: { from: pos, to: pos, insert: normalized },
							selection: { anchor: pos + normalized.length }
						})
						currentOutputLength += normalized.length
						// 动态更新高亮范围
						updateHighlight(outputStartPos, outputStartPos + currentOutputLength)
					}
				} else {
					// 续写模式：追加到末尾
					appendAtEnd(normalized)
					currentOutputLength += normalized.length
					// 动态更新高亮范围
					updateHighlight(outputStartPos, outputStartPos + currentOutputLength)
				}
			}
			if (chunk.length > accumulated.length) accumulated = chunk
		},
		() => {
			aiLoading.value = false
			streamHandle = null
			try {
				if (!replaceMode) {
					let text = getText() || ''
					// 压缩恰好两个换行为一个，>=3 不动
					text = text.replace(/\n+/g, m => (m.length === 2 ? '\n' : m))
					setText(text)
				}
			} catch {}
			console.log('✅ [AI] 生成完成，高亮已保留（点击编辑器任意位置可清除）')
			ElMessage.success(`${taskName}完成！`)
		},
		(error) => {
			aiLoading.value = false
			streamHandle = null
			clearHighlight()
			console.error(`${taskName}失败:`, error)
			ElMessage.error(`${taskName}失败`)
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
		// 调用 extractParticipantsWithTypeForCurrentChapter
		let participants = extractParticipantsWithTypeForCurrentChapter()
		const chapterText = getText() || ''
		// 上下文相关的stage_overview等信息由右栏ContextPanel处理
		let stageOverview = ''
		try {
			if ((props.contextParams as any)?.stage_overview) {
				stageOverview = String((props.contextParams as any).stage_overview || '')
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

// 处理来自ChapterToolsPanel的提取事件
function handleExtractDynamicInfoEvent(e: CustomEvent) {
	const payload = (e as any)?.detail
	if (payload?.llm_config_id) {
		extractDynamicInfoWithLlm(payload.llm_config_id)
	}
}

function handleExtractRelationsEvent(e: CustomEvent) {
	const payload = (e as any)?.detail
	if (payload?.llm_config_id) {
		extractRelationsWithLlm(payload.llm_config_id)
	}
}

async function extractRelationsWithLlm(llmConfigId: number) {
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

onMounted(() => {
	initEditor()
	loadPrompts()
	try {
		const title = props.card?.title || ''
		const vol = Number((props.contextParams as any)?.volume_number ?? (props.card as any)?.content?.volume_number ?? NaN)
		const ch = Number((props.contextParams as any)?.chapter_number ?? (props.card as any)?.content?.chapter_number ?? NaN)
		editorStore.setCurrentContextInfo({ title, volume: Number.isNaN(vol) ? null : vol, chapter: Number.isNaN(ch) ? null : ch })
	} catch {}
	
	// 监听提取事件
	window.addEventListener('nf:extract-dynamic-info', handleExtractDynamicInfoEvent as any)
	window.addEventListener('nf:extract-relations', handleExtractRelationsEvent as any)
	
	// ESC 键关闭右键菜单
	window.addEventListener('keydown', handleKeyDown)
})

function handleClickOutside(e: MouseEvent) {
	if (!contextMenu.visible) return
	const target = e.target as HTMLElement
	// 点击菜单外部时关闭
	if (!target.closest('.context-menu-popup')) {
		closeContextMenu()
	}
}

// 按 ESC 键关闭菜单
function handleKeyDown(e: KeyboardEvent) {
	if (contextMenu.visible && e.key === 'Escape') {
		closeContextMenu()
	}
}

onUnmounted(() => {
	// 移除右键菜单监听器
	if (cmRoot.value) {
		const editorDom = cmRoot.value.querySelector('.cm-editor') as HTMLElement
		if (editorDom) {
			editorDom.removeEventListener('contextmenu', handleEditorContextMenu)
		}
	}
	
	try { view?.destroy() } catch {}
	editorStore.setApplyChapterReplacements(null)
	try { streamHandle?.cancel(); } catch {}
	
	// 移除事件监听
	window.removeEventListener('nf:extract-dynamic-info', handleExtractDynamicInfoEvent as any)
	window.removeEventListener('nf:extract-relations', handleExtractRelationsEvent as any)
	window.removeEventListener('keydown', handleKeyDown)
	
	// 清理右键菜单的点击监听器（如果还在）
	if (contextMenuClickListenerAdded) {
		window.removeEventListener('click', handleClickOutside, { capture: true })
		contextMenuClickListenerAdded = false
	}
})

// 恢复历史版本内容
async function restoreContent(versionContent: any) {
	try {
		// 提取章节正文内容
		const textContent = typeof versionContent === 'string' 
			? versionContent 
			: (versionContent?.content || '')
		
		// 更新编辑器内容
		setText(textContent)
		
		// 更新 localCard.content 的各个字段（保持响应式）
		if (typeof versionContent === 'object') {
			Object.assign(localCard.content, versionContent)
		}
		// 确保 content 字段是正确的文本
		localCard.content.content = textContent
		
		// 更新原始内容（避免触发dirty）
		originalContent.value = textContent
		isDirty.value = false
		emit('update:dirty', false)
		
		// 更新字数
		wordCount.value = computeWordCount(textContent)
		
	} catch (e) {
		console.error('Failed to restore content:', e)
		throw e
	}
}

// 暴露方法供父组件调用
defineExpose({
	handleSave,
	restoreContent
})
</script>

<style scoped>
/* 提示词下拉菜单项 */
.prompt-item {
	display: flex;
	justify-content: space-between;
	align-items: center;
	width: 100%;
}

.check-icon {
	color: var(--el-color-primary);
	font-size: 16px;
	margin-left: 8px;
}

/* 高亮选中的提示词 */
:deep(.is-selected) {
	background-color: var(--el-color-primary-light-9);
	color: var(--el-color-primary);
	font-weight: 600;
}

/* 最外层容器：固定高度，防止整体滚动 */
.chapter-studio { 
	display: flex; 
	flex-direction: column; 
	height: 100%; 
	min-height: 0;
	overflow: hidden; /* 关键：防止整体滚动 */
}

.toolbar {
	padding: 8px 20px;
	border-bottom: 1px solid var(--el-border-color-light);
	background: var(--el-fill-color-lighter);
	display: flex;
	flex-direction: column;
	flex-shrink: 0;
	box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

.toolbar-row {
	display: flex;
	align-items: center;
	gap: 12px;
	flex-wrap: nowrap;
}

.toolbar-divider {
	width: 1px;
	height: 20px;
	background: var(--el-border-color-light);
	margin: 0 4px;
}

.toolbar-group {
	display: flex;
	align-items: center;
	gap: 6px;
	padding: 4px 10px;
	background: var(--el-fill-color-blank);
	border-radius: 6px;
	border: 1px solid var(--el-border-color-lighter);
}

.group-label {
	font-size: 12px;
	color: var(--el-text-color-secondary);
	margin-right: 4px;
	font-weight: 500;
}

.flex-spacer { 
	flex-grow: 1; 
}

.editor-content-wrapper {
	flex: 1;
	display: flex;
	flex-direction: column;
	min-height: 0; /* 允许flex子元素正确收缩 */
	overflow: hidden; /* 防止wrapper本身滚动 */
}

.chapter-header {
	padding: 16px 32px 14px;
	border-bottom: 1px solid var(--el-border-color-light);
	background: var(--el-fill-color-lighter);
	display: flex;
	align-items: center;
	flex-shrink: 0;
}

.title-section {
	flex: 1;
	display: flex;
	align-items: center;
	gap: 16px;
}

.chapter-title {
	margin: 0;
	font-size: 28px;
	font-weight: 600;
	color: var(--el-text-color-primary);
	line-height: 1.4;
	outline: none;
	padding: 6px 12px;
	border-radius: 6px;
	transition: all 0.2s ease;
	cursor: text;
	flex: 1;
}

.chapter-title:hover {
	background-color: var(--el-fill-color-light);
}

.chapter-title:focus {
	background-color: var(--el-fill-color);
	box-shadow: 0 0 0 2px var(--el-color-primary-light-7);
}

.title-meta {
	display: flex;
	align-items: center;
	gap: 6px;
	color: var(--el-text-color-secondary);
	font-size: 14px;
	white-space: nowrap;
}

.word-count-icon {
	font-size: 16px;
}

.word-count-text {
	font-weight: 500;
}

.editor-content {
	flex: 1 1 0; /* flex-basis为0，避免被内容撑开 */
	min-height: 0; /* 允许flex子元素正确收缩和滚动 */
	overflow: hidden; 
	background-color: var(--el-bg-color);
	position: relative; 
}

/* CodeMirror 内部样式 */
.editor-content :deep(.cm-editor) {
	height: 100% !important; /* 强制占满容器高度，不自动扩展 */
	outline: none;
	line-height: 1.8;
	color: var(--el-text-color-primary);
	background-color: transparent;
}

/* 确保 CodeMirror 的滚动容器正确工作 */
.editor-content :deep(.cm-scroller) {
	overflow-y: auto !important; /* 强制垂直滚动 */
	overflow-x: auto !important;
	max-height: 100% !important; /* 防止超出父容器 */
}
.editor-content :deep(.cm-content) {
	padding: 20px;
	color: var(--el-text-color-primary);
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
.event-meta {
	color: var(--el-text-color-secondary);
	margin-left: 8px;
}

/* 右键快速编辑菜单 */
.context-menu-popup {
	position: fixed;
	z-index: 9999;
	background: var(--el-bg-color-overlay);
	border: 1px solid var(--el-border-color);
	border-radius: 8px;
	box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
	padding: 12px;
	min-width: 280px;
	max-width: 400px;
	animation: fadeInScale 0.15s ease-out;
}

@keyframes fadeInScale {
	from {
		opacity: 0;
		transform: scale(0.95);
	}
	to {
		opacity: 1;
		transform: scale(1);
	}
}

.context-menu-compact {
	display: flex;
	justify-content: center;
}

.context-menu-expanded {
	display: flex;
	flex-direction: column;
}

.context-menu-actions {
	display: flex;
	gap: 8px;
	justify-content: space-between;
}

.context-menu-actions .el-button {
	flex: 1;
}

/* 自定义 AI 高亮效果 */
.editor-content :deep(.cm-ai-highlight) {
	background: linear-gradient(120deg, 
		rgba(96, 165, 250, 0.2) 0%, 
		rgba(129, 140, 248, 0.2) 50%, 
		rgba(96, 165, 250, 0.2) 100%);
	background-size: 200% 100%;
	animation: highlightPulse 2s ease-in-out infinite;
	border-radius: 2px;
	padding: 2px 0;
	box-shadow: 0 0 0 1px rgba(96, 165, 250, 0.3);
}

@keyframes highlightPulse {
	0%, 100% {
		background-position: 0% 50%;
	}
	50% {
		background-position: 100% 50%;
	}
}

/* 暗色模式下的高亮 */
.dark .editor-content :deep(.cm-ai-highlight) {
	background: linear-gradient(120deg, 
		rgba(59, 130, 246, 0.25) 0%, 
		rgba(99, 102, 241, 0.25) 50%, 
		rgba(59, 130, 246, 0.25) 100%);
	background-size: 200% 100%;
	box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.4);
}
</style>