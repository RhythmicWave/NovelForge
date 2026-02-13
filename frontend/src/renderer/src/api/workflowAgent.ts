import { API_BASE_URL } from './request'
import request from './request'
import { createSSEStreamingRequest } from './streaming'
import type { components } from '@renderer/types/generated'


export type WorkflowAgentMode = components['schemas']['WorkflowAgentMode']
export type WorkflowAgentChatRequest = components['schemas']['WorkflowAgentChatRequest']
export type WorkflowPatchOp = components['schemas']['WorkflowPatchOp']
export type WorkflowPatchRequest = components['schemas']['WorkflowPatchRequest']
export type WorkflowPatchResponse = components['schemas']['WorkflowPatchResponse']


function createWorkflowAgentStreamingRequest(
  body: WorkflowAgentChatRequest,
  onEvent: (evt: any) => void,
  onClose: () => void,
  onError?: (err: any) => void,
) {
  return createSSEStreamingRequest({
    endpoint: `${API_BASE_URL}/workflow-agent/chat`,
    body,
    onClose,
    onError,
    onMessage: wrapper => {
      if (typeof wrapper?.content === 'string' && wrapper.content.length) {
        try {
          const payload = JSON.parse(wrapper.content)
          onEvent(payload)
        } catch {
          onEvent({ type: 'token', data: { text: wrapper.content, delta: true } })
        }
      }
    },
  })
}


export function workflowAgentChatStreaming(
  body: WorkflowAgentChatRequest,
  onEvent: (evt: any) => void,
  onClose: () => void,
  onError?: (err: any) => void,
) {
  return createWorkflowAgentStreamingRequest(body, onEvent, onClose, onError)
}


export async function applyWorkflowPatch(
  workflowId: number,
  body: WorkflowPatchRequest,
): Promise<WorkflowPatchResponse> {
  return request.post<WorkflowPatchResponse>(`/workflows/${workflowId}/patch`, body, '/api', { showLoading: false })
}
