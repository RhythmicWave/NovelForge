import request from './request'

export type ReviewType = 'chapter' | 'stage' | 'card' | 'custom'
export type ReviewTargetType = 'card'
export type QualityGate = 'pass' | 'revise' | 'block'

export interface ReviewRunRequest {
  card_id: number
  project_id?: number
  title: string
  target_type?: ReviewTargetType
  review_type?: ReviewType
  review_profile?: string
  target_field?: string
  target_text?: string
  context_info?: string
  facts_info?: string
  content_snapshot?: string | null
  llm_config_id: number
  prompt_name?: string
  temperature?: number
  max_tokens?: number
  timeout?: number
  meta?: Record<string, unknown>
}

export interface ReviewDraftResult {
  review_text: string
  quality_gate: QualityGate
  review_type: ReviewType
  review_profile: string
  review_target_field?: string | null
  prompt_name: string
  llm_config_id?: number | null
  target_snapshot?: string | null
  existing_review_card_id?: number | null
  review_card_title: string
  meta?: Record<string, unknown>
}

export interface ReviewResultCard {
  card_id: number
  project_id: number
  title: string
  review_target_card_id: number
  review_target_title: string
  review_target_type: ReviewTargetType
  review_type: ReviewType
  review_profile: string
  review_target_field?: string | null
  quality_gate: QualityGate
  review_markdown: string
  prompt_name: string
  llm_config_id?: number | null
  reviewed_at: string
  target_snapshot?: string | null
  meta?: Record<string, unknown>
  created_at: string
}

export interface ReviewCardUpsertRequest {
  project_id: number
  target_card_id: number
  target_title: string
  review_type: ReviewType
  review_profile: string
  target_field?: string | null
  review_text: string
  quality_gate: QualityGate
  prompt_name: string
  llm_config_id?: number | null
  content_snapshot?: string | null
  meta?: Record<string, unknown>
}

export interface ReviewRunResponse {
  review_text: string
  draft: ReviewDraftResult
}

interface ReviewRequestOptions {
  signal?: AbortSignal
}

function resolveReviewTimeoutMs(timeoutSeconds?: number): number {
  const fallbackMs = 300_000
  if (typeof timeoutSeconds !== 'number' || !Number.isFinite(timeoutSeconds) || timeoutSeconds <= 0) {
    return fallbackMs
  }
  return Math.max(fallbackMs, Math.ceil(timeoutSeconds * 1000) + 30_000)
}

export function runReview(
  payload: ReviewRunRequest,
  options?: ReviewRequestOptions
): Promise<ReviewRunResponse> {
  return (request as any).request({
    method: 'POST',
    url: '/api/chapter-reviews/cards/run',
    data: payload,
    showLoading: false,
    signal: options?.signal,
    timeout: resolveReviewTimeoutMs(payload.timeout),
  })
}

export function upsertReviewCard(payload: ReviewCardUpsertRequest): Promise<ReviewResultCard> {
  return request.post<ReviewResultCard>('/chapter-reviews/cards/upsert', payload, '/api', {
    showLoading: false,
  })
}

export function listTargetReviewCards(cardId: number): Promise<ReviewResultCard[]> {
  return request.get<ReviewResultCard[]>(
    `/chapter-reviews/cards/${cardId}`,
    undefined,
    '/api',
    { showLoading: false }
  )
}

export function deleteReviewCard(reviewCardId: number): Promise<boolean> {
  return request.delete<boolean>(`/chapter-reviews/${reviewCardId}`, undefined, '/api', { showLoading: false })
}
