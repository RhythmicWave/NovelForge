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

// 构建树并输出先序顺序（按每层 display_order 排序），用于“全局之前”判定
function buildPreorder(cards: CardRead[]): CardRead[] {
  type Node = CardRead & { children: Node[] }
  const map = new Map<number, Node>()
  const nodes: Node[] = cards.map(c => ({ ...(c as CardRead), children: [] }))
  nodes.forEach(n => map.set(n.id, n))
  const roots: Node[] = []
  nodes.forEach(n => {
    if (n.parent_id && map.has(n.parent_id)) map.get(n.parent_id)!.children.push(n)
    else roots.push(n)
  })
  const sortRec = (arr: Node[]) => {
    arr.sort((a, b) => a.display_order - b.display_order)
    arr.forEach(ch => sortRec(ch.children))
  }
  sortRec(roots)
  const out: CardRead[] = []
  const visit = (arr: Node[]) => {
    for (const n of arr) { out.push(n); if ((n as any).children?.length) visit((n as any).children) }
  }
  visit(roots)
  return out
}

function extractVolumeNumberFromTitle(title?: string): number | undefined {
  if (!title) return undefined
  const m = title.match(/^第(\d+)卷$/)
  if (m) return parseInt(m[1], 10)
  return undefined
}

function getVolumeNumberFromCard(card?: CardRead): number | undefined {
  if (!card) return undefined
  const c = card.content as any
  const toNum = (v: any) => {
    const n = Number(v)
    return Number.isFinite(n) ? n : undefined
  }
  const byTop = toNum(c?.volume_number)
  if (byTop !== undefined) return byTop
  const byOutline = toNum(c?.volume_outline?.volume_number)
  if (byOutline !== undefined) return byOutline
  const byChapter = toNum(c?.chapter_outline?.volume_number)
  if (byChapter !== undefined) return byChapter
  return extractVolumeNumberFromTitle(card.title)
}

// 兼容多种 VolumeOutline 包装：volume_outline/VolumeOutline/volumeOutline/volume_outline_response/VolumeOutlineResponse
function unwrapVolumeOutline(content: any): any {
  if (!content || typeof content !== 'object') return {}
  if (content.volume_outline && typeof content.volume_outline === 'object') return content.volume_outline
  if (content.VolumeOutline && typeof content.VolumeOutline === 'object') return content.VolumeOutline
  if (content.volumeOutline && typeof content.volumeOutline === 'object') return content.volumeOutline
  if (content.volume_outline_response && typeof content.volume_outline_response === 'object') return content.volume_outline_response
  if (content.VolumeOutlineResponse && typeof content.VolumeOutlineResponse === 'object') return content.VolumeOutlineResponse
  // 若 content 本身包含 VolumeOutline 的典型字段，直接返回
  const hallmark = ['stage_lines','main_target','thinking','character_snapshot','branch_line']
  const keys = Object.keys(content)
  if (keys.some(k => hallmark.includes(k))) return content
  return {}
}

function getChapterNumberFromCard(card?: CardRead): number | undefined {
  if (!card) return undefined
  const c = card.content as any
  const toNum = (v: any) => {
    const n = Number(v)
    return Number.isFinite(n) ? n : undefined
  }
  const nTop = toNum(c?.chapter_number)
  if (nTop !== undefined) return nTop
  const n = toNum(c?.chapter_outline?.chapter_number)
  if (n !== undefined) return n
  return undefined
}

function buildVars(ctx: ResolveContext): ResolveVars {
  const v: ResolveVars = {}
  v.currentCard = ctx.currentCard
  v.volumeNumber = getVolumeNumberFromCard(ctx.currentCard)
  v.chapterNumber = getChapterNumberFromCard(ctx.currentCard)
  return v
}

function evalIndexExpr(expr: string, vars: ResolveVars, ctx?: ResolveContext, candidatesLen?: number): number | 'last' | undefined {
  const trimmed = (expr || '').trim()
  if (trimmed === 'last' || trimmed === 'first') return trimmed === 'last' ? 'last' : 1
  // 负数：从末尾倒数，例如 -1 表示最后一个
  if (/^-[0-9]+$/.test(trimmed)) {
    const neg = parseInt(trimmed, 10) // negative
    if (typeof candidatesLen === 'number') return Math.max(1, candidatesLen + 1 + neg)
    return undefined
  }
  // $self.<path>(±int)
  const mSelf = trimmed.match(/^\$self\.(.+?)(?:\s*([+-])\s*(\d+))?$/)
  if (mSelf && ctx?.currentCard) {
    const base = Number(getPathValue(ctx.currentCard, mSelf[1]))
    if (!isNaN(base)) {
      const delta = mSelf[2] && mSelf[3] ? (mSelf[2] === '+' ? parseInt(mSelf[3], 10) : -parseInt(mSelf[3], 10)) : 0
      return base + delta
    }
  }
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

function parseMultiPathSpec(path?: string): { mode: 'single' | 'multi'; paths: string[] } {
  if (!path) return { mode: 'single', paths: [] }
  // .{a,b,c} 或 已去掉前导点后的 {a,b,c}
  const trimmed = path.replace(/^\./, '')
  const m = trimmed.match(/^\{(.+)\}$/)
  if (m) {
    const raw = m[1]
    const parts = raw.split(',').map(s => s.trim()).filter(Boolean)
    return { mode: 'multi', paths: parts }
  }
  return { mode: 'single', paths: [trimmed] }
}

function pickFields(obj: any, paths: string[]): any {
  const out: Record<string, any> = {}
  for (const p of paths) {
    const val = getPathValue(obj, p)
    const key = p.split('.').pop() || p
    out[key] = val
  }
  return out
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
  const raw = (vol?.content as any) || {}
  const vo = unwrapVolumeOutline(raw)
  const stageLines = Array.isArray(vo?.stage_lines) ? vo.stage_lines : []
  if (!Array.isArray(stageLines) || stageLines.length === 0) return undefined
  const ch = Number(vars.chapterNumber)
  if (!Number.isFinite(ch)) return undefined
  return stageLines.find((s: any) => {
    const ref = s?.reference_chapter
    if (!Array.isArray(ref) || ref.length < 2) return false
    const start = Number(ref[0])
    const end = Number(ref[1])
    return Number.isFinite(start) && Number.isFinite(end) && ch >= start && ch <= end
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

  // 优先处理特殊选择器，避免被标题规则误匹配
  if (token.startsWith('stage:current')) {
    const path = token.includes('.') ? token.substring('stage:current.'.length) : ''
    const stage = resolveCurrentStage(ctx.cards, vars)
    const value = getPathValue(stage, path)
    return stringifyValue(value)
  }
  if (token === 'chapters:previous') {
    const arr = resolvePreviousChapters(ctx.cards, vars)
    return stringifyValue(arr)
  }

  // type 选择器
  const typeMatch = token.match(/^type:([^\.\[\s]+)(?:\[([^\]]+)\])?(?:\.(.+))?$/)
  if (typeMatch) {
    const typeName = typeMatch[1]
    const filter = typeMatch[2]
    const rawPath = typeMatch[3]
    const { mode: pathMode, paths: multiPaths } = parseMultiPathSpec(rawPath)

    // 使用树的先序顺序，保证“无论层级”的全局顺序与左侧树一致
    const orderedAll = buildPreorder(ctx.cards)

    // previous: 全局之前（可选参数 n：仅返回最后 n 个）
    if (filter && filter.startsWith('previous')) {
      const mPrev = filter.match(/^previous(?::(\d+))?$/)
      const takeN = mPrev && mPrev[1] ? parseInt(mPrev[1], 10) : undefined
      const indexById = new Map<number, number>()
      orderedAll.forEach((c, i) => indexById.set(c.id, i))
      const currentIndex = ctx.currentCard ? (indexById.get(ctx.currentCard.id) ?? -1) : -1
      let prevList = orderedAll.filter((c, i) => c.card_type?.name === typeName && i < currentIndex)
      if (typeof takeN === 'number' && takeN > 0 && prevList.length > takeN) {
        prevList = prevList.slice(-takeN)
      }
      if (!rawPath) {
        const collected = prevList.map(c => getPathValue(c, 'content'))
        return stringifyValue(collected)
      }
      if (pathMode === 'multi') {
        const collected = prevList.map(c => pickFields(c, multiPaths))
        return stringifyValue(collected)
      } else {
        const collected = prevList.map(c => getPathValue(c, multiPaths[0]))
        return stringifyValue(collected)
      }
    }

    // sibling: 同父节点下的同类型卡片（按 display_order）
    if (filter === 'sibling') {
      const pid = ctx.currentCard?.parent_id ?? null
      const siblings = ctx.cards.filter(c => c.parent_id === pid && c.card_type?.name === typeName && c.id !== ctx.currentCard?.id)
        .sort((a, b) => a.display_order - b.display_order)
      if (!rawPath) {
        const collected = siblings.map(c => getPathValue(c, 'content'))
        return stringifyValue(collected)
      }
      if (pathMode === 'multi') return stringifyValue(siblings.map(c => pickFields(c, multiPaths)))
      return stringifyValue(siblings.map(c => getPathValue(c, multiPaths[0])))
    }

    // 其他情况：以稳定排序供 first/last/index 使用
    const rawCandidates = orderedAll.filter(c => c.card_type?.name === typeName)
    let candidates = [...rawCandidates]
    candidates = candidates.sort((a, b) => {
      const na = extractVolumeNumberFromTitle(a.title)
      const nb = extractVolumeNumberFromTitle(b.title)
      if (na != null && nb != null) return na - nb
      return a.display_order - b.display_order
    })

    let selected: CardRead | undefined
    if (filter === 'last') selected = candidates[candidates.length - 1]
    else if (filter === 'first' || !filter) selected = candidates[0]
    else if (filter && filter.startsWith('index=')) {
      const expr = filter.substring('index='.length)
      const idx = evalIndexExpr(expr, vars, ctx, candidates.length)
      if (idx === 'last') selected = candidates[candidates.length - 1]
      else if (typeof idx === 'number') {
        if (idx < 1 || idx > candidates.length) return ''
        selected = candidates[idx - 1]
      }
    }

    if (!selected) selected = candidates[0]

    if (!rawPath) {
      const value = getPathValue(selected, 'content')
      return stringifyValue(value)
    }
    if (pathMode === 'multi') {
      const obj = pickFields(selected, multiPaths)
      return stringifyValue(obj)
    } else {
      const value = getPathValue(selected, multiPaths[0])
      return stringifyValue(value)
    }
  }

  // self / parent 选择器
  const selfMatch = token.match(/^self(?:\.(.+))?$/)
  if (selfMatch) {
    const raw = selfMatch[1]
    const { mode: pathMode, paths: multiPaths } = parseMultiPathSpec(raw)
    if (!raw) return stringifyValue(getPathValue(ctx.currentCard, 'content'))
    if (pathMode === 'multi') {
      const obj = pickFields(ctx.currentCard, multiPaths)
      return stringifyValue(obj)
    } else {
      const value = getPathValue(ctx.currentCard, multiPaths[0])
      return stringifyValue(value)
    }
  }
  const parentMatch = token.match(/^parent(?:\.(.+))?$/)
  if (parentMatch) {
    const raw = parentMatch[1]
    const parent = selectParent(ctx.cards, ctx.currentCard)
    const { mode: pathMode, paths: multiPaths } = parseMultiPathSpec(raw)
    if (!raw) return stringifyValue(getPathValue(parent, 'content'))
    if (pathMode === 'multi') {
      const obj = pickFields(parent, multiPaths)
      return stringifyValue(obj)
    } else {
      const value = getPathValue(parent, multiPaths[0])
      return stringifyValue(value)
    }
  }

  // 标题选择（向后兼容），显式排除特殊前缀
  if (!token.startsWith('stage:') && !token.startsWith('chapters:')) {
    const titleMatch = token.match(/^([^\.\[\s]+)(?:\.(.+))?$/)
    if (titleMatch) {
      const title = titleMatch[1]
      const raw = titleMatch[2]
      const card = selectByTitle(ctx.cards, title)
      if (!raw) return stringifyValue(getPathValue(card, 'content'))
      const { mode: pathMode, paths: multiPaths } = parseMultiPathSpec(raw)
      if (pathMode === 'multi') {
        const obj = pickFields(card, multiPaths)
        return stringifyValue(obj)
      } else {
        const value = getPathValue(card, multiPaths[0])
        return stringifyValue(value)
      }
    }
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