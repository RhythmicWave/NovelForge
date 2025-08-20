import http from './request'
import type { components } from '@renderer/types/generated'

// 使用后端生成的类型（注意部分为 Input/Output 变体）
export type UpdateDynamicInfoOutput = components['schemas']['UpdateDynamicInfo-Output']
export type RelationExtractionOutput = components['schemas']['RelationExtraction-Output']

export interface ExtractOnlyRequest {
	project_id?: number
	text: string
	participants?: string[]
	llm_config_id: number
	timeout?: number
	extra_context?: string
}

export function extractDynamicInfoOnly(data: ExtractOnlyRequest) {
	return http.post<UpdateDynamicInfoOutput>('/memory/extract-dynamic-info', data)
}

export type UpdateDynamicInfoOnlyReq = components['schemas']['UpdateDynamicInfoRequest']
export type UpdateDynamicInfoOnlyResp = components['schemas']['UpdateDynamicInfoResponse']

export function updateDynamicInfoOnly(data: UpdateDynamicInfoOnlyReq) {
	return http.post<UpdateDynamicInfoOnlyResp>('/memory/update-dynamic-info', data)
}

// 入图关系（LLM抽取→Graphiti/Neo4j写入，一步到位）
export type IngestRelationsLLMRequest = components['schemas']['IngestRelationsLLMRequest']
export type IngestRelationsLLMResponse = components['schemas']['IngestRelationsLLMResponse']
export function ingestRelationsLLM(data: IngestRelationsLLMRequest) {
	return http.post<IngestRelationsLLMResponse>('/memory/ingest-relations-llm', data)
}

// 预览→确认入图：使用后端 RelationExtraction-Output
export type ExtractRelationsOnlyReq = components['schemas']['ExtractRelationsRequest']
export function extractRelationsOnly(data: ExtractRelationsOnlyReq) {
	return http.post<RelationExtractionOutput>('/memory/extract-relations-llm', data)
}

export type IngestRelationsFromPreviewReq = components['schemas']['IngestRelationsFromPreviewRequest']
export type IngestRelationsFromPreviewResp = components['schemas']['IngestRelationsFromPreviewResponse']
export function ingestRelationsFromPreview(data: IngestRelationsFromPreviewReq) {
	return http.post<IngestRelationsFromPreviewResp>('/memory/ingest-relations', data)
} 