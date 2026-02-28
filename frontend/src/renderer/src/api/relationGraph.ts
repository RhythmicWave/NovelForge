import http from './request'
import type { components } from '@renderer/types/generated'

export type RelationGraphKey = components['schemas']['RelationGraphKey']
export type RelationGraphEvent = components['schemas']['RelationGraphEvent']
export type RelationGraphInput = components['schemas']['RelationGraphInput']
export type RelationGraphRecord = components['schemas']['RelationGraphRecord']

export type RelationGraphListRequest = components['schemas']['RelationGraphListRequest']
export type RelationGraphListResponse = components['schemas']['RelationGraphListResponse']

export type RelationGraphUpsertRequest = components['schemas']['RelationGraphUpsertRequest']
export type RelationGraphDeleteRequest = components['schemas']['RelationGraphDeleteRequest']
export type RelationGraphWriteResponse = components['schemas']['RelationGraphWriteResponse']

export type RelationGraphBatchDeleteRequest = components['schemas']['RelationGraphBatchDeleteRequest']
export type RelationGraphBatchUpdateKindRequest = components['schemas']['RelationGraphBatchUpdateKindRequest']
export type RelationGraphBatchUpdateStanceRequest = components['schemas']['RelationGraphBatchUpdateStanceRequest']
export type RelationGraphBatchAppendEventsRequest = components['schemas']['RelationGraphBatchAppendEventsRequest']
export type RelationGraphBatchCreateRequest = components['schemas']['RelationGraphBatchCreateRequest']

export type RelationGraphExportRequest = components['schemas']['RelationGraphExportRequest']
export type RelationGraphExportResponse = components['schemas']['RelationGraphExportResponse']
export type RelationGraphImportRequest = components['schemas']['RelationGraphImportRequest']
export type RelationGraphImportResponse = components['schemas']['RelationGraphImportResponse']

export function listRelationGraph(data: RelationGraphListRequest) {
  return http.post<RelationGraphListResponse>('/relation-graph/list', data)
}

export function upsertRelationGraph(data: RelationGraphUpsertRequest) {
  return http.post<RelationGraphRecord>('/relation-graph/upsert', data)
}

export function deleteRelationGraph(data: RelationGraphDeleteRequest) {
  return http.post<RelationGraphWriteResponse>('/relation-graph/delete', data)
}

export function batchDeleteRelationGraph(data: RelationGraphBatchDeleteRequest) {
  return http.post<RelationGraphWriteResponse>('/relation-graph/batch/delete', data)
}

export function batchUpdateKindRelationGraph(data: RelationGraphBatchUpdateKindRequest) {
  return http.post<RelationGraphWriteResponse>('/relation-graph/batch/update-kind', data)
}

export function batchUpdateStanceRelationGraph(data: RelationGraphBatchUpdateStanceRequest) {
  return http.post<RelationGraphWriteResponse>('/relation-graph/batch/update-stance', data)
}

export function batchAppendEventsRelationGraph(data: RelationGraphBatchAppendEventsRequest) {
  return http.post<RelationGraphWriteResponse>('/relation-graph/batch/append-events', data)
}

export function batchCreateRelationGraph(data: RelationGraphBatchCreateRequest) {
  return http.post<RelationGraphWriteResponse>('/relation-graph/batch/create', data)
}

export function exportRelationGraph(data: RelationGraphExportRequest) {
  return http.post<RelationGraphExportResponse>('/relation-graph/export', data)
}

export function importRelationGraph(data: RelationGraphImportRequest) {
  return http.post<RelationGraphImportResponse>('/relation-graph/import', data)
}
