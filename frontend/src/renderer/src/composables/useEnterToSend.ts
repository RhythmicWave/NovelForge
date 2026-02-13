import type { Ref } from 'vue'

interface UseEnterToSendOptions {
  canSend: Readonly<Ref<boolean>>
  onSend: () => void
  streaming?: Readonly<Ref<boolean>>
  allowWhileStreaming?: boolean
}

export function useEnterToSend(options: UseEnterToSendOptions) {
  return (event: KeyboardEvent) => {
    if (event.key !== 'Enter') return
    if (event.shiftKey || event.isComposing) return

    event.preventDefault()

    if (!options.allowWhileStreaming && options.streaming?.value) {
      return
    }
    if (!options.canSend.value) {
      return
    }

    options.onSend()
  }
}
