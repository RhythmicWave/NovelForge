export interface SSERequestParams {
  endpoint: string
  body: any
  onMessage: (payload: any) => void
  onClose: (event: SSECloseEvent) => void
  onError?: (err: any) => void
}

export type SSECloseReason = 'done' | 'error' | 'eof' | 'aborted'

export interface SSECloseEvent {
  reason: SSECloseReason
  terminalType?: string
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
  let terminalType: string | null = null
  let closeNotified = false

  function inspectTerminalPayload(payload: any): void {
    const candidates: any[] = [payload]
    if (typeof payload?.content === 'string') {
      try {
        candidates.push(JSON.parse(payload.content))
      } catch {
        // Plain text chunks are not protocol events.
      }
    }

    for (const candidate of candidates) {
      const type = candidate && typeof candidate.type === 'string' ? candidate.type : ''
      if (type === 'done' || type === 'error' || type === 'cancelled') {
        terminalType = type
        return
      }
    }
  }

  function notifyClose(reason: SSECloseReason): void {
    if (closeNotified) return
    closeNotified = true
    const effectiveReason = terminalType === 'done' && reason === 'aborted' ? 'done' : reason
    onClose({ reason: effectiveReason, terminalType: terminalType || undefined })
  }

  function handleTransportError(error: any): void {
    // 一旦收到协议终止事件，后续 reader 错误只反映连接收尾过程，不能
    // 覆盖已经确定的业务结果。
    if (terminalType === 'done') {
      notifyClose('done')
      return
    }
    if (terminalType === 'error' || terminalType === 'cancelled') {
      notifyClose('error')
      return
    }
    if (!closeNotified) onError?.(error)
  }

  function dispatchEventBlock(eventBlock: string): void {
    const lines = eventBlock.split(/\r?\n/).map(line => line.trim())
    const dataLines = lines
      .filter(line => line.startsWith('data:'))
      .map(line => line.slice(5).trimStart())
    if (!dataLines.length) return

    try {
      const payload = JSON.parse(dataLines.join(''))
      inspectTerminalPayload(payload)
      onMessage(payload)
    } catch {
      // Ignore malformed SSE frames and keep reading the connection.
    }
  }

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
          buffer += decoder.decode()
          if (buffer.trim()) {
            dispatchEventBlock(buffer)
            buffer = ''
          }
          if (terminalType === 'done') {
            notifyClose('done')
          } else if (terminalType === 'error' || terminalType === 'cancelled') {
            notifyClose('error')
          } else {
            notifyClose('eof')
          }
          return
        }

        buffer += decoder.decode(value, { stream: true })
        const events = buffer.split(/\r?\n\r?\n/)
        buffer = events.pop() || ''

        for (const evt of events) {
          dispatchEventBlock(evt)
        }

        pump()
      }).catch(error => {
        if (error?.name === 'AbortError') {
          notifyClose('aborted')
          return
        }
        handleTransportError(error)
      })
    }

    pump()
  }).catch(error => {
    if (error?.name === 'AbortError') {
      notifyClose('aborted')
      return
    }
    handleTransportError(error)
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
