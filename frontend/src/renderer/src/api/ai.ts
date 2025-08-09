import { aiHttpClient } from './request'
import type { components } from '@renderer/types/generated'

export type GeneralAIRequest = components['schemas']['GeneralAIRequest']
export type ContinuationRequest = components['schemas']['ContinuationRequest']
export type ContinuationResponse = components['schemas']['ContinuationResponse']

// Manually define AIConfigOptions if it's not in generated types
export interface AIConfigOptions {
  llm_configs: Array<{ id: number; display_name: string }>
  prompts: Array<{ id: number; name: string; description: string | null }>
  available_tasks?: string[]
  response_models: string[]
}


export function generateAIContent(
  params: GeneralAIRequest
): Promise<any> { // The response can be any of the Pydantic models
  return aiHttpClient.post<any>('/ai/generate', params)
}

// 3. 获取AI配置选项
export function getAIConfigOptions(): Promise<AIConfigOptions> {
  return aiHttpClient.get<AIConfigOptions>('/ai/config-options')
}

// 4. 续写接口
export function generateContinuation(params: ContinuationRequest): Promise<ContinuationResponse> {
  return aiHttpClient.post<ContinuationResponse>('/ai/generate/continuation', params)
} 

// 5. 续写流式接口（SSE）
export function generateContinuationStreaming(
    params: ContinuationRequest, 
    onData: (data: string) => void, 
    onClose: () => void,
    onError?: (err: any) => void
) {
  // Use fetch for better streaming support
  const API_BASE_URL = 'http://127.0.0.1:8000/api' // Adjust if your base URL is different
  
  fetch(`${API_BASE_URL}/ai/generate/continuation`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream'
    },
    body: JSON.stringify(params)
  }).then(response => {
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    if (!response.body) {
        throw new Error('Response body is null');
    }
    const reader = response.body.getReader();

    const decoder = new TextDecoder();

    function push() {
      reader.read().then(({ done, value }) => {
        if (done) {
          onClose();
          return;
        }
        
        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\\n');

        for (const line of lines) {
            if (line.startsWith('data: ')) {
                try {
                    const jsonData = JSON.parse(line.substring(6));
                    if (jsonData.content) {
                        onData(jsonData.content);
                    }
                } catch (e) {
                    // Ignore incomplete JSON
                }
            }
        }
        push();
      }).catch(err => {
        if (onError) onError(err);
      });
    }
    push();

  }).catch(err => {
    if (onError) onError(err);
  });
} 