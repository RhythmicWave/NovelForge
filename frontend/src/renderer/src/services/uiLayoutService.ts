export interface SectionConfig {
  title: string
  include?: string[]
  exclude?: string[]
  description?: string
  collapsed?: boolean
}

interface LayoutSources {
  schemaMeta?: Record<string, any>
  backendLayout?: SectionConfig[] | undefined
  frontendDefault?: SectionConfig[] | undefined
}

// 简单合并策略：schemaMeta>backend>frontend
export function mergeSections(sources: LayoutSources): SectionConfig[] | undefined {
  if (sources.schemaMeta && Array.isArray(sources.schemaMeta.sections)) {
    return normalizeSections(sources.schemaMeta.sections)
  }
  if (sources.backendLayout && sources.backendLayout.length) return normalizeSections(sources.backendLayout)
  if (sources.frontendDefault && sources.frontendDefault.length) return normalizeSections(sources.frontendDefault)
  return undefined
}

function normalizeSections(sections: any[]): SectionConfig[] {
  return sections.map(s => ({
    title: String(s.title ?? '分区'),
    include: s.include ? [...s.include] : undefined,
    exclude: s.exclude ? [...s.exclude] : undefined,
    description: s.description,
    collapsed: !!s.collapsed,
  }))
}

export function autoGroup(schema: any): SectionConfig[] {
  const props: Record<string, any> = schema?.properties || {}
  const keys = Object.keys(props)
  const objectKeys = keys.filter(k => resolveType(props[k]) === 'object')
  const arrayKeys = keys.filter(k => resolveType(props[k]) === 'array')
  const scalarKeys = keys.filter(k => !['object','array'].includes(resolveType(props[k])))

  const sections: SectionConfig[] = []
  if (scalarKeys.length) sections.push({ title: '基础信息', include: scalarKeys })
  for (const k of objectKeys) sections.push({ title: k, include: [k] })
  for (const k of arrayKeys) sections.push({ title: k, include: [k], collapsed: true })
  return sections
}

function resolveType(s: any): string {
  if (!s) return 'object'
  if (s.anyOf) {
    const first = s.anyOf.find((x: any) => x && x.type && x.type !== 'null')
    if (first) return first.type
  }
  if (s.$ref) return 'object'
  return s.type || 'object'
} 