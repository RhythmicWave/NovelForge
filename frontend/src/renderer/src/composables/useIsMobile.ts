import { onBeforeUnmount, readonly, ref } from 'vue'

/** 窄屏断点：低于此宽度时编辑器切换为单栏 + 抽屉式侧栏 */
export const MOBILE_BREAKPOINT = 900

/**
 * 响应式的窄屏判断。基于 matchMedia，比监听 resize 省事件也省重排。
 * 在没有 matchMedia 的环境（SSR / 测试）下固定返回 false。
 */
export function useIsMobile() {
  const isMobile = ref(false)

  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return { isMobile: readonly(isMobile) }
  }

  const query = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT}px)`)
  isMobile.value = query.matches

  const onChange = (event: MediaQueryListEvent) => {
    isMobile.value = event.matches
  }
  query.addEventListener('change', onChange)
  onBeforeUnmount(() => query.removeEventListener('change', onChange))

  return { isMobile: readonly(isMobile) }
}
