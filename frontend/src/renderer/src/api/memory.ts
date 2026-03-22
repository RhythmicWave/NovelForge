import http from './request'
import type { components } from '@renderer/types/generated'

// 使用后端生成的类型（注意部分为 Input/Output 变体）
export type UpdateDynamicInfoOutput = components['schemas']['UpdateDynamicInfo-Output']
export type RelationExtractionOutput = components['schemas']['RelationExtraction-Output']
export interface ParticipantTyped {
	name: string
	type: string
}

export interface MemoryExtractorInfo {
	code: string
	name: string
	target: string
	preview_supported: boolean
}

export interface ExtractPreviewRequest {
	project_id?: number
	extractor_code: string
	text: string
	participants?: ParticipantTyped[]
	llm_config_id: number
	temperature?: number
	max_tokens?: number
	timeout?: number
	extra_context?: string
	volume_number?: number
	chapter_number?: number
}

export interface ExtractPreviewResponse {
	extractor_code: string
	preview_data: Record<string, any>
	affected_targets: Array<Record<string, any>>
}

export interface ApplyPreviewRequest {
	project_id: number
	extractor_code: string
	data: Record<string, any>
	options?: Record<string, any>
	participants?: ParticipantTyped[]
	volume_number?: number
	chapter_number?: number
}

export interface ApplyPreviewResponse {
	success: boolean
	written: number
	updated_card_count: number
	updated_relation_count: number
	affected_targets: Array<Record<string, any>>
	raw_result: Record<string, any>
}

export interface ExtractOnlyRequest {
	project_id?: number
	text: string
	participants?: ParticipantTyped[]
	llm_config_id: number
	temperature?: number
	max_tokens?: number
	timeout?: number
	extra_context?: string
	volume_number?: number
	chapter_number?: number
}

export function extractDynamicInfoOnly(data: ExtractOnlyRequest) {
	return extractMemoryPreview({
		project_id: data.project_id,
		extractor_code: 'character_dynamic',
		text: data.text,
		participants: data.participants,
		llm_config_id: data.llm_config_id,
		temperature: data.temperature,
		max_tokens: data.max_tokens,
		timeout: data.timeout,
		extra_context: data.extra_context,
		volume_number: data.volume_number,
		chapter_number: data.chapter_number,
	}).then(res => res.preview_data as UpdateDynamicInfoOutput)
}

export interface UpdateDynamicInfoOnlyReq {
	project_id: number
	data: UpdateDynamicInfoOutput
	queue_size?: number
}
export type UpdateDynamicInfoOnlyResp = components['schemas']['UpdateDynamicInfoResponse']

export function updateDynamicInfoOnly(data: UpdateDynamicInfoOnlyReq) {
	return applyMemoryPreview({
		project_id: data.project_id,
		extractor_code: 'character_dynamic',
		data: data.data as Record<string, any>,
		options: { queue_size: data.queue_size ?? 5 },
	}).then(res => ({
		success: res.success,
		updated_card_count: res.updated_card_count,
	} as UpdateDynamicInfoOnlyResp))
}

export function listExtractors() {
	return http.get<{ items: MemoryExtractorInfo[] }>('/memory/extractors')
}

export function extractMemoryPreview(data: ExtractPreviewRequest) {
	return http.post<ExtractPreviewResponse>('/memory/extract-preview', data, '/api', { showLoading: false })
}

export function applyMemoryPreview(data: ApplyPreviewRequest) {
	return http.post<ApplyPreviewResponse>('/memory/apply-preview', data, '/api', { showLoading: false })
}

// 入图关系（LLM抽取→Graphiti/Neo4j写入，一步到位）
export type IngestRelationsLLMRequest = components['schemas']['IngestRelationsLLMRequest']
export type IngestRelationsLLMResponse = components['schemas']['IngestRelationsLLMResponse']
export function ingestRelationsLLM(data: IngestRelationsLLMRequest) {
	return http.post<IngestRelationsLLMResponse>('/memory/ingest-relations-llm', data)
}

// 预览→确认入图：使用后端 RelationExtraction-Output
export interface ExtractRelationsOnlyReq {
	text: string
	participants?: ParticipantTyped[]
	llm_config_id: number
	temperature?: number
	max_tokens?: number
	timeout?: number
	volume_number?: number
	chapter_number?: number
}
export function extractRelationsOnly(data: ExtractRelationsOnlyReq) {
	return extractMemoryPreview({
		project_id: undefined,
		extractor_code: 'relation',
		text: data.text,
		participants: data.participants as ParticipantTyped[] | undefined,
		llm_config_id: data.llm_config_id,
		temperature: data.temperature,
		max_tokens: data.max_tokens,
		timeout: data.timeout ?? undefined,
		volume_number: data.volume_number ?? undefined,
		chapter_number: data.chapter_number ?? undefined,
	}).then(res => res.preview_data as RelationExtractionOutput)
}

export type IngestRelationsFromPreviewReq = components['schemas']['IngestRelationsFromPreviewRequest']
export type IngestRelationsFromPreviewResp = components['schemas']['IngestRelationsFromPreviewResponse']
export function ingestRelationsFromPreview(data: IngestRelationsFromPreviewReq) {
	return applyMemoryPreview({
		project_id: data.project_id,
		extractor_code: 'relation',
		data: data.data as Record<string, any>,
		volume_number: data.volume_number ?? undefined,
		chapter_number: data.chapter_number ?? undefined,
	}).then(res => ({ written: res.written } as IngestRelationsFromPreviewResp))
}
