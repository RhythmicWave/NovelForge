/**
 * 安全的 localStorage 读写工具。
 *
 * localStorage 在隐私模式、配额超限、sandbox 等场景下会抛异常
 * （QuotaExceededError / SecurityError），若不捕获会中断调用方主流程。
 * 这里统一兜底，保证存储异常不会向上传播。
 */

/** 读取字符串，异常或不存在时返回 fallback。 */
export function safeGetItem(key: string, fallback = ''): string {
  try {
    const value = localStorage.getItem(key)
    return value === null ? fallback : value
  } catch {
    return fallback
  }
}

/** 写入字符串，异常时静默忽略。 */
export function safeSetItem(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    // ignore localStorage errors
  }
}

/** 读取并解析为数字；非法、缺失或异常时返回 fallback。 */
export function safeGetNumber(key: string, fallback: number, allowedValues?: readonly number[]): number {
  const raw = safeGetItem(key, '')
  if (raw === '') return fallback
  const parsed = Number(raw)
  if (!Number.isFinite(parsed)) return fallback
  return allowedValues && !allowedValues.includes(parsed) ? fallback : parsed
}

/** 移除指定键，异常时静默忽略。 */
export function safeRemoveItem(key: string): void {
  try {
    localStorage.removeItem(key)
  } catch {
    // ignore localStorage errors
  }
}
