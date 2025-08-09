import type { CardRead } from '@renderer/api/cards'

// 上下文解析变量
export interface ResolveVars {
  currentCard?: CardRead
  // 当前卷号（优先从内容字段读取，其次从标题解析）
  volumeNumber?: number
  // 当前章节号（若存在）
  chapterNumber?: number
}

export interface ResolveContext {
  template: string
  cards: CardRead[]
  currentCard?: CardRead
}

function extractVolumeNumberFromTitle(title?: string): number | undefined {
  if (!title) return undefined
  const m = title.match(/^第(\d+)卷$/)
  if (m) return parseInt(m[1], 10)
  return undefined
}

function getVolumeNumberFromCard(card?: CardRead): number | undefined {
  if (!card) return undefined
  // 尝试从常见数据结构中提取
  const c = card.content as any
  const byOutline = c?.volume_outline?.volume_number
  if (typeof byOutline === 'number' && !isNaN(byOutline)) return byOutline
  const byChapter = c?.chapter_outline?.volume_number
  if (typeof byChapter === 'number' && !isNaN(byChapter)) return byChapter
  // 退回标题解析
  return extractVolumeNumberFromTitle(card.title)
}

function getChapterNumberFromCard(card?: CardRead): number | undefined {
  if (!card) return undefined
  const c = card.content as any
  const n = c?.chapter_outline?.chapter_number
  if (typeof n === 'number' && !isNaN(n)) return n
  return undefined
}

function buildVars(ctx: ResolveContext): ResolveVars {
  const v: ResolveVars = {}
  v.currentCard = ctx.currentCard
  v.volumeNumber = getVolumeNumberFromCard(ctx.currentCard)
  v.chapterNumber = getChapterNumberFromCard(ctx.currentCard)
  return v
}

function evalIndexExpr(expr: string, vars: ResolveVars): number | 'last' | undefined {
  // 支持: 数字, last, $current.volumeNumber-1 / +1 等简单算术
  const trimmed = expr.trim()
  if (trimmed === 'last' || trimmed === 'first') return trimmed === 'last' ? 'last' : 1
  // $current.volumeNumber±int
  const vm = vars.volumeNumber
  const m = trimmed.match(/^\$current\.volumeNumber\s*([+-])\s*(\d+)$/)
  if (m && typeof vm === 'number') {
    const op = m[1]
    const n = parseInt(m[2], 10)
    return op === '+' ? vm + n : vm - n
  }
  // $current.chapterNumber
  if (trimmed === '$current.chapterNumber' && typeof vars.chapterNumber === 'number') return vars.chapterNumber
  // 纯数字
  if (/^\d+$/.test(trimmed)) return parseInt(trimmed, 10)
  // 直接 $current.volumeNumber
  if (trimmed === '$current.volumeNumber' && typeof vm === 'number') return vm
  return undefined
}

function selectByType(cards: CardRead[], typeName: string): CardRead[] {
  return cards.filter(c => c.card_type?.name === typeName)
}

function selectByTitle(cards: CardRead[], title: string): CardRead | undefined {
  return cards.find(c => c.title === title)
}

function selectParent(cards: CardRead[], card?: CardRead): CardRead | undefined {
  if (!card?.parent_id) return undefined
  return cards.find(c => c.id === card.parent_id)
}

function getPathValue(obj: any, path?: string): any {
  if (!path || path.length === 0) return obj
  return path.split('.').reduce((acc, part) => (acc != null ? acc[part] : undefined), obj)
}

function stringifyValue(val: any): string {
  if (val == null) return ''
  if (typeof val === 'object') return JSON.stringify(val, null, 2)
  return String(val)
}

// 辅助：获取当前卷的分卷大纲卡片
function getCurrentVolumeCard(cards: CardRead[], vars: ResolveVars): CardRead | undefined {
  if (typeof vars.volumeNumber !== 'number') return undefined
  const list = selectByType(cards, '分卷大纲')
  const sorted = [...list].sort((a, b) => {
    const na = extractVolumeNumberFromTitle(a.title)
    const nb = extractVolumeNumberFromTitle(b.title)
    if (na != null && nb != null) return na - nb
    return a.display_order - b.display_order
  })
  return sorted[vars.volumeNumber - 1]
}

// stage:current -> 在当前卷的 stage_lines 中找到覆盖当前章节号的阶段
function resolveCurrentStage(cards: CardRead[], vars: ResolveVars): any {
  const vol = getCurrentVolumeCard(cards, vars)
  const stageLines = (vol?.content as any)?.volume_outline?.stage_lines || []
  if (!Array.isArray(stageLines)) return undefined
  const ch = vars.chapterNumber
  if (typeof ch !== 'number') return undefined
  return stageLines.find((s: any) => {
    const ref = s?.reference_chapter
    if (!Array.isArray(ref) || ref.length < 2) return false
    const start = Number(ref[0])
    const end = Number(ref[1])
    return !isNaN(start) && !isNaN(end) && ch >= start && ch <= end
  })
}

// chapters:previous -> 当前卷、当前阶段内，章节号小于当前章节的已存在章节卡片，映射为 SmallChapter
function resolvePreviousChapters(cards: CardRead[], vars: ResolveVars): any[] {
  const volNum = vars.volumeNumber
  const chNum = vars.chapterNumber
  if (typeof volNum !== 'number' || typeof chNum !== 'number') return []
  // 所有章节大纲卡片
  const chapterCards = selectByType(cards, '章节大纲')
  // 过滤当前卷、且小于当前章节号
  const filtered = chapterCards.filter(c => {
    const cc = c.content as any
    const vol = cc?.chapter_outline?.volume_number
    const cn = cc?.chapter_outline?.chapter_number
    return vol === volNum && typeof cn === 'number' && cn < chNum
  })
  // 映射为 SmallChapter 结构
  return filtered
    .sort((a, b) => {
      const an = (a.content as any)?.chapter_outline?.chapter_number || 0
      const bn = (b.content as any)?.chapter_outline?.chapter_number || 0
      return an - bn
    })
    .map(c => {
      const cc = (c.content as any)?.chapter_outline || {}
      return {
        title: cc.title,
        chapter_number: cc.chapter_number,
        overview: cc.overview,
        enemy: cc.enemy || null,
        resolve_enemy: cc.resolve_enemy || null,
      }
    })
}

function resolveToken(rawToken: string, ctx: ResolveContext, vars: ResolveVars): string {
  // 支持三种前缀：type:、self、标题（默认）以及 parent
  // 语法：
  // @type:分卷大纲[index=last].content.volume_outline
  // @type:分卷大纲[index=$current.volumeNumber-1].content
  // @self.parent.content
  // @核心蓝图.content

  const token = rawToken.replace(/^@/, '')

  // type 选择器
  const typeMatch = token.match(/^type:([^\.\[\s]+)(?:\[([^\]]+)\])?(?:\.(.+))?$/)
  if (typeMatch) {
    const typeName = typeMatch[1]
    const filter = typeMatch[2] // e.g., index=last | index=3 | index=$current.volumeNumber-1
    const path = typeMatch[3]

    let candidates = selectByType(ctx.cards, typeName)
    // 默认按 display_order 排序；若标题形如“第N卷”，按 N 排序
    candidates = [...candidates].sort((a, b) => {
      const na = extractVolumeNumberFromTitle(a.title)
      const nb = extractVolumeNumberFromTitle(b.title)
      if (na != null && nb != null) return na - nb
      return a.display_order - b.display_order
    })

    let selected: CardRead | undefined
    if (filter && filter.startsWith('index=')) {
      const expr = filter.substring('index='.length)
      const idx = evalIndexExpr(expr, vars)
      if (idx === 'last') selected = candidates[candidates.length - 1]
      else if (typeof idx === 'number') selected = candidates[idx - 1] // 1-based
    }
    // 未提供 index 则取 first
    if (!selected) selected = candidates[0]

    const value = getPathValue(selected, path)
    return stringifyValue(value)
  }

  // self / parent 选择器
  const selfMatch = token.match(/^self(?:\.(.+))?$/)
  if (selfMatch) {
    const path = selfMatch[1]
    const value = getPathValue(ctx.currentCard, path)
    return stringifyValue(value)
  }
  const parentMatch = token.match(/^parent(?:\.(.+))?$/)
  if (parentMatch) {
    const path = parentMatch[1]
    const parent = selectParent(ctx.cards, ctx.currentCard)
    const value = getPathValue(parent, path)
    return stringifyValue(value)
  }

  // 标题选择（向后兼容）
  const titleMatch = token.match(/^([^\.\[\s]+)(?:\.(.+))?$/)
  if (titleMatch) {
    const title = titleMatch[1]
    const path = titleMatch[2]
    const card = selectByTitle(ctx.cards, title)
    const value = getPathValue(card, path)
    return stringifyValue(value)
  }

  // 当前阶段选择器
  if (token.startsWith('stage:current')) {
    const path = token.includes('.') ? token.substring('stage:current.'.length) : ''
    const stage = resolveCurrentStage(ctx.cards, vars)
    const value = getPathValue(stage, path)
    return stringifyValue(value)
  }

  // 之前章节列表（SmallChapter数组）
  if (token === 'chapters:previous') {
    const arr = resolvePreviousChapters(ctx.cards, vars)
    return stringifyValue(arr)
  }

  return `[Error: Invalid reference '${rawToken}']`
}

export function resolveTemplate(ctx: ResolveContext): string {
  const vars = buildVars(ctx)
  const { template } = ctx
  if (!template) return ''

  // 粗略拆分 token：以空白作为分隔，提取以 @ 开头的片段
  const tokenRegex = /@([^\s]+)/g
  let result = template
  const matches = [...template.matchAll(tokenRegex)]
  // 为避免嵌套替换偏移，从后往前替换
  for (let i = matches.length - 1; i >= 0; i--) {
    const m = matches[i]
    const full = '@' + m[1]
    const replacement = resolveToken(full, ctx, vars)
    result = result.slice(0, m.index!) + replacement + result.slice(m.index! + full.length)
  }
  return result
} 