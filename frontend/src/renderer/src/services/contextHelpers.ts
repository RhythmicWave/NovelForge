export function unwrapChapterOutline(obj: any): any {
  if (!obj || typeof obj !== 'object') return {}
  // 常见包装键
  if (obj.chapter_outline && typeof obj.chapter_outline === 'object') return obj.chapter_outline
  if (obj.ChapterOutline && typeof obj.ChapterOutline === 'object') return obj.ChapterOutline
  if (obj.chapterOutline && typeof obj.chapterOutline === 'object') return obj.chapterOutline
  // 直接识别：出现关键字段即可视为章节大纲形态
  const hallmark = ['volume_number', 'chapter_number', 'character_list', 'overview', 'characters', 'participants', 'roles']
  const keys = Object.keys(obj || {})
  return keys.some(k => hallmark.includes(k)) ? obj : {}
}

// 统一清洗姓名：去除括号备注、全角/半角空格、尾部顿号等
export function sanitizeName(raw: string): string {
  if (!raw) return ''
  let s = String(raw).trim()
  // 去掉全角空格
  s = s.replace(/\u3000/g, ' ')
  s = s.replace(/\s+/g, ' ').trim()
  // 去除括号及其中内容（中英文括号）
  s = s.replace(/[（(][^）)]*[）)]/g, '').trim()
  // 去掉末尾的无意义符号
  s = s.replace(/[、，。,.]+$/g, '').trim()
  return s
}

export function toNameList(arr: any): string[] {
  if (!Array.isArray(arr)) return []
  if (arr.every(x => typeof x === 'string')) return (arr as string[]).map(s => sanitizeName(s)).filter(Boolean)
  const out: string[] = []
  for (const it of arr) {
    if (typeof it === 'object' && it) {
      const cand = (it.name || it.title || it.label || '').toString().trim()
      if (cand) out.push(sanitizeName(cand))
    }
  }
  return Array.from(new Set(out))
}

export function extractParticipantsFrom(obj: any): string[] {
  if (!obj || typeof obj !== 'object') return []
  const keys = ['character_list','characters','participants','roles','人物列表','角色列表']
  for (const k of keys) {
    if (k in obj) {
      const names = toNameList((obj as any)[k])
      if (names.length) return names
    }
  }
  return []
} 