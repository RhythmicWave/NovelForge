import { nextTick, ref } from 'vue'

interface MessageListLike {
  scrollToBottom: () => void
}

export function useMessageListScroll() {
  const messageListRef = ref<MessageListLike | null>(null)

  function scrollToBottom() {
    nextTick(() => {
      messageListRef.value?.scrollToBottom()
    })
  }

  return {
    messageListRef,
    scrollToBottom,
  }
}

