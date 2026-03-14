import request from './request'

export interface PreviousChapterInput {
  title: string
  volume_number?: number | null
  chapter_number?: number | null
  content: string
}

export interface PreviousStageInput {
  title: string
  stage_name?: string | null
  volume_number?: number | null
  stage_number?: number | null
  reference_chapter?: number[]
  overview: string
  analysis?: string | null
  entity_snapshot?: string[]
}

export interface StageChapterOutlineInput {
  title: string
  chapter_number?: number | null
  overview: string
  entity_list?: string[]
  has_content?: boolean
  word_count?: number | null
}

export interface ChapterReviewRunRequest {
  card_id: number
  project_id?: number
  title: string
  chapter_content: string
  volume_number?: number | null
  chapter_number?: number | null
  participants?: string[]
  previous_chapters?: PreviousChapterInput[]
  context_info?: string
  facts_info?: string
  content_snapshot?: string | null
  llm_config_id: number
  prompt_name?: string
  temperature?: number
  max_tokens?: number
  timeout?: number
}

export interface StageReviewRunRequest {
  card_id: number
  project_id?: number
  title: string
  stage_name?: string | null
  volume_number?: number | null
  stage_number?: number | null
  reference_chapter?: number[]
  analysis?: string
  overview?: string
  entity_snapshot?: string[]
  chapter_outlines?: StageChapterOutlineInput[]
  previous_stages?: PreviousStageInput[]
  context_info?: string
  facts_info?: string
  content_snapshot?: string | null
  llm_config_id: number
  prompt_name?: string
  temperature?: number
  max_tokens?: number
  timeout?: number
}

interface ReviewRequestOptions {
  signal?: AbortSignal
}

export interface ReviewRecord {
  id: number
  project_id: number
  review_type: 'chapter' | 'stage'
  target_type: 'card'
  target_id: number
  target_title?: string | null
  prompt_name: string
  llm_config_id?: number | null
  quality_gate: 'pass' | 'revise' | 'block' | string
  result_text: string
  content_snapshot?: string | null
  created_at: string
}

export interface ChapterReviewRunResponse {
  review_text: string
  record: ReviewRecord
}

export interface StageReviewRunResponse {
  review_text: string
  record: ReviewRecord
}

export function runChapterReview(
  payload: ChapterReviewRunRequest,
  options?: ReviewRequestOptions
): Promise<ChapterReviewRunResponse> {
  return request.post<ChapterReviewRunResponse>('/chapter-reviews/run', payload, '/api', {
    showLoading: false,
    signal: options?.signal,
  })
}

export function runStageReview(
  payload: StageReviewRunRequest,
  options?: ReviewRequestOptions
): Promise<StageReviewRunResponse> {
  return request.post<StageReviewRunResponse>('/chapter-reviews/stage/run', payload, '/api', {
    showLoading: false,
    signal: options?.signal,
  })
}

export function listChapterReviews(cardId: number): Promise<ReviewRecord[]> {
  return request.get<ReviewRecord[]>(`/chapter-reviews/cards/${cardId}`, undefined, '/api', { showLoading: false })
}

export function listProjectReviews(
  projectId: number,
  reviewType: 'all' | 'chapter' | 'stage' = 'all',
  targetTitle?: string
): Promise<ReviewRecord[]> {
  return request.get<ReviewRecord[]>(
    `/chapter-reviews/projects/${projectId}`,
    {
      review_type: reviewType,
      target_title: targetTitle?.trim() || undefined,
    },
    '/api',
    { showLoading: false }
  )
}

export function deleteReview(reviewId: number): Promise<boolean> {
  return request.delete<boolean>(`/chapter-reviews/${reviewId}`, undefined, '/api', { showLoading: false })
}
