export interface SSERequestParams {
  endpoint: string
  body: any
  onMessage: (payload: any) => void
  onClose: () => void
  onError?: (err: any) => void
}

function extractErrorMessage(response: Response, fallback: string): Promise<string> {
  return (async () => {
    try {
      const contentType = response.headers.get('content-type') || ''
      if (contentType.includes('application/json')) {
        const data = await response.json()
        const detail = data?.detail
        if (typeof detail === 'string') return detail
        if (detail?.message) return detail.message
        return data?.message || fallback
      }
      const text = await response.text()
      return text || fallback
    } catch {
      return fallback
    }
  })()
}

export function createSSEStreamingRequest(params: SSERequestParams) {
  const { endpoint, body, onMessage, onClose, onError } = params
  const controller = new AbortController()
  const signal = controller.signal

  fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream',
    },
    body: JSON.stringify(body),
    signal,
  }).then(async response => {
    if (!response.ok) {
      const message = await extractErrorMessage(response, `请求失败：${response.status}`)
      throw new Error(message)
    }

    if (!response.body) {
      throw new Error('Response body is null')
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    function pump() {
      reader.read().then(({ done, value }) => {
        if (done) {
          onClose()
          return
        }

        buffer += decoder.decode(value, { stream: true })
        const events = buffer.split('\n\n')
        buffer = events.pop() || ''

        for (const evt of events) {
          const lines = evt.split('\n').map(line => line.trim())
          const dataLines = lines
            .filter(line => line.startsWith('data: '))
            .map(line => line.slice(6))
          if (!dataLines.length) continue

          try {
            const payload = JSON.parse(dataLines.join(''))
            onMessage(payload)
          } catch {
            // ignore malformed chunk
          }
        }

        pump()
      }).catch(error => {
        if (error?.name === 'AbortError') {
          onClose()
          return
        }
        onError?.(error)
      })
    }

    pump()
  }).catch(error => {
    if (error?.name === 'AbortError') {
      onClose()
      return
    }
    onError?.(error)
  })

  return {
    cancel: () => {
      try {
        controller.abort()
      } catch {
        // noop
      }
    },
  }
}
