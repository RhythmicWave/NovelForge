export interface BuilderField {
  name: string
  label?: string
  kind: 'string' | 'number' | 'integer' | 'boolean' | 'relation' | 'tuple'
  isArray?: boolean
  required?: boolean
  relation: { targetModelName: string | null }
  description?: string
  example?: string
  // tuple element types（仅用于 Builder 展示与生成简单元组）
  tupleItems?: Array<'string' | 'number' | 'integer' | 'boolean'>
}

function toStringExample(val: any): string {
  if (val === undefined || val === null) return ''
  if (typeof val === 'string') return val
  try { return JSON.stringify(val) } catch { return String(val) }
}

function parseMaybeJSON(s: string): any {
  if (!s) return undefined
  const t = s.trim()
  try { return JSON.parse(t) } catch { return t }
}

export function schemaToBuilder(schema: any): BuilderField[] {
  const props = schema?.properties || {}
  const required: string[] = schema?.required || []
  const fields: BuilderField[] = []
  // 允许带 $defs，但此函数只解析主 properties → relation 的 $ref 名称
  for (const key of Object.keys(props)) {
    const p = props[key]
    const isArray = p?.type === 'array'
    const core = isArray ? p.items : p
    let kind: BuilderField['kind'] = 'string'
    let relation: BuilderField['relation'] = { targetModelName: null }
    let tupleItems: BuilderField['tupleItems'] | undefined = undefined
    if (core?.$ref) {
      kind = 'relation'
      const refName = String(core.$ref).split('/').pop() || null
      relation = { targetModelName: refName }
    } else if (core && (Array.isArray(core.prefixItems) || Array.isArray(core.anyOf))) {
      kind = 'tuple'
      const arr = (core.prefixItems || core.anyOf || []) as any[]
      tupleItems = arr.map((s: any) => (['string','number','integer','boolean'].includes(s?.type) ? s.type : 'string'))
    } else if (core?.type && ['string','number','integer','boolean'].includes(core.type)) {
      kind = core.type
    }

    // examples[0] 优先，否则 example
    const exs = core?.examples || p?.examples
    let exRaw: any = ''
    if (Array.isArray(exs) && exs.length) exRaw = exs[0]
    else if (core?.example !== undefined) exRaw = core.example
    else if (p?.example !== undefined) exRaw = p.example

    fields.push({
      name: key,
      label: core?.title || key,
      kind,
      isArray,
      required: required.includes(key),
      relation,
      description: core?.description || p?.description || '',
      example: toStringExample(exRaw),
      tupleItems,
    })
  }
  return fields
}

export function builderToSchema(fields: BuilderField[]): any {
  const properties: Record<string, any> = {}
  const required: string[] = []
  const defs: Record<string, any> = {}
  for (const f of fields) {
    if (!f.name) continue
    let node: any = {}
    if (f.kind === 'relation') {
      if (f.isArray) node = { type: 'array', items: { $ref: `#/$defs/${f.relation.targetModelName ?? ''}` } }
      else node = { $ref: `#/$defs/${f.relation.targetModelName ?? ''}` }
    } else if (f.kind === 'tuple') {
      const items = (f.tupleItems && f.tupleItems.length)
        ? f.tupleItems.map(t => ({ type: t }))
        : [{ type: 'string' }, { type: 'string' }]
      const core = { type: 'array', prefixItems: items, minItems: items.length, maxItems: items.length }
      node = f.isArray ? { type: 'array', items: core } : core
    } else {
      node = { type: f.kind }
      if (f.isArray) node = { type: 'array', items: { type: f.kind } }
    }
    node.title = f.label || f.name
    if (f.description) node.description = f.description
    if (f.example && f.example.trim()) {
      node.example = f.example
      node.examples = [parseMaybeJSON(f.example)]
    }
    properties[f.name] = node
    if (f.required) required.push(f.name)
  }
  const schema: any = { type: 'object', properties }
  if (required.length) schema.required = required
  // defs 由调用方（SchemaStudio）收集/注入，以便跨模型复用
  return schema
} 