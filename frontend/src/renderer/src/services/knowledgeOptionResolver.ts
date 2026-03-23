import { listKnowledge } from '@renderer/api/setting'

type KnowledgeCache = {
  loaded: boolean
  byName: Map<string, string>
}

let cachePromise: Promise<KnowledgeCache> | null = null

function stripAnnotation(label: string): string {
  return label.replace(/\s*[\uFF08(][^\uFF08\uFF09()]*[\uFF09)]\s*$/, '').trim()
}

function parseKnowledgeOptions(text: string): string[] {
  const options: string[] = []

  for (const rawLine of (text || '').split(/\r?\n/)) {
    const line = rawLine.trim()
    if (!line || line === '```') {
      continue
    }

    const bulletMatch = line.match(/^[-*]\s+(.+)$/)
    const numberedMatch = line.match(/^\d+[.)]\s+(.+)$/)
    const content = bulletMatch?.[1] || numberedMatch?.[1]
    if (!content) {
      continue
    }

    const value = stripAnnotation(content)
    if (value) {
      options.push(value)
    }
  }

  return Array.from(new Set(options))
}

async function loadKnowledgeCache(): Promise<KnowledgeCache> {
  if (!cachePromise) {
    cachePromise = listKnowledge()
      .then((items) => {
        const byName = new Map<string, string>()
        for (const item of items || []) {
          if (!item?.name) {
            continue
          }
          byName.set(item.name, item.content || '')
        }
        return { loaded: true, byName }
      })
      .catch(() => ({ loaded: false, byName: new Map<string, string>() }))
  }
  return cachePromise
}

export async function resolveKnowledgeOptions(knowledgeName: string): Promise<string[]> {
  if (!knowledgeName) {
    return []
  }

  const cache = await loadKnowledgeCache()
  const content = cache.byName.get(knowledgeName)
  if (!content) {
    return []
  }

  return parseKnowledgeOptions(content)
}

export function resetKnowledgeOptionCache(): void {
  cachePromise = null
}
