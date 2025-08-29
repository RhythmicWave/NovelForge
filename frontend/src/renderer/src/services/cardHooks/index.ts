// 通用卡片钩子注册与分发器
// 说明：每个卡片类型对应一个 hooks 文件（同目录），通过副作用 registerHook 完成注册。

import { type CardRead } from '@renderer/api/cards'

// 钩子存储：按类型名注册与分发
type HookFn = (card: CardRead, ctx: any) => Promise<void> | void
const hooksByTypeName: Record<string, HookFn> = {}

export function registerHook(typeName: string, hook: HookFn) {
  hooksByTypeName[typeName] = hook
}

let loaded = false
async function ensureHooksLoaded() {
  if (loaded) return
  loaded = true
  // 自动注册：加载当前目录下除 index.ts 外的所有钩子模块
  const loaders: Record<string, () => Promise<unknown>> = import.meta.glob([
    './*.ts',
    '!./index.ts',
  ])
  await Promise.all(Object.values(loaders).map((loader) => loader()))
}

async function runAfterSave(card: CardRead, ctx: any) {
  await ensureHooksLoaded()

  const typeName = (card.card_type as any)?.name as string | undefined
  const hook = typeName ? hooksByTypeName[typeName] : undefined

  if (hook) {
    await hook(card, ctx)
  }
}

export const cardHooks = { runAfterSave } 