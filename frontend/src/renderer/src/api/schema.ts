import request from './request'
import { ref } from 'vue'

// --- 类型定义 ---
// 基础的 JSON Schema 类型定义。可以根据需要进行扩展。
export interface JSONSchema {
  type: 'string' | 'number' | 'integer' | 'boolean' | 'object' | 'array' | 'null'
  title?: string
  description?: string
  default?: any
  properties?: { [key: string]: JSONSchema }
  required?: string[]
  items?: JSONSchema // 用于数组
  // 用于 Pydantic v2+ 的元组（Tuple）
  prefixItems?: JSONSchema[]
  // 用于 Pydantic v1 的元组（Tuple）或联合类型（Union）
  anyOf?: JSONSchema[]
  // 用于 Literal 转换来的枚举
  enum?: (string | number)[]
  // 用于对象引用
  $ref?: string
}

// --- 状态 ---
const schemas = ref<Map<string, JSONSchema>>(new Map())
const isLoading = ref(false)
const error = ref<any>(null)

// --- 逻辑 ---

/**
 * 解析 $ref 引用，找到其对应的 schema 定义。
 * @param refPath 引用路径 (例如, '#/components/schemas/MyModel')
 * @param openapiSpec 完整的 OpenAPI 规范对象。
 * @returns 解析后的 JSONSchema，如果未找到则返回 null。
 */
function resolveRef(refPath: string, allSchemas: Map<string, JSONSchema>): JSONSchema | null {
  // 我们只处理指向 allSchemas 中其他定义的引用
  // 假设格式为 '#/$defs/MyModel' or 'MyModel'
  const refName = refPath.split('/').pop()
  if (!refName) {
    console.error('无效的 $ref 路径:', refPath)
    return null
  }
  const resolved = allSchemas.get(refName)
  if (!resolved) {
    console.error(`无法在 allSchemas 中解析 $ref: ${refName}`)
        return null
      }
  return resolved
}

/**
 * 递归地解析 schema 中的所有 $ref 引用。
 * @param schema 要解析的 JSONSchema。
 * @param allSchemas 包含所有可用 schema 定义的 Map。
 * @param visited 已访问的引用路径，用于防止循环引用。
 * @returns 解析后的 JSONSchema。
 */
function dereferenceSchema(
  schema: JSONSchema,
  allSchemas: Map<string, JSONSchema>,
  visited = new Set<string>()
): JSONSchema {
  if (typeof schema !== 'object' || schema === null) {
    return schema
  }

  if (schema.$ref) {
    if (visited.has(schema.$ref)) {
      console.warn('检测到循环引用:', schema.$ref)
      return { type: 'object', title: 'Circular Reference' }
    }
    visited.add(schema.$ref)
    const resolved = resolveRef(schema.$ref, allSchemas)
    if (resolved) {
      // 递归地解析解析后的 schema
      return dereferenceSchema(resolved, allSchemas, visited)
    } else {
      return { type: 'string', title: `Unresolved Reference: ${schema.$ref}` }
    }
  }

  const newSchema = { ...schema }
  if (newSchema.properties) {
    newSchema.properties = Object.fromEntries(
      Object.entries(newSchema.properties).map(([key, propSchema]) => [
        key,
        dereferenceSchema(propSchema, allSchemas, new Set(visited))
      ])
    )
  }

  if (newSchema.items) {
    newSchema.items = dereferenceSchema(newSchema.items, allSchemas, new Set(visited))
  }
  
  if (newSchema.prefixItems) {
    newSchema.prefixItems = newSchema.prefixItems.map(itemSchema => 
      dereferenceSchema(itemSchema, allSchemas, new Set(visited))
    );
  }

  if (newSchema.anyOf) {
    newSchema.anyOf = newSchema.anyOf.map(itemSchema => 
      dereferenceSchema(itemSchema, allSchemas, new Set(visited))
    );
  }

  return newSchema
}


/**
 * 获取完整的 OpenAPI 规范并填充 schemas Map。
 * 这个函数应该在应用启动时被调用一次。
 */
async function loadSchemas() {
  if (schemas.value.size > 0 || isLoading.value) {
    return
  }
  isLoading.value = true
  error.value = null
  try {
    // 改为从专用端点获取所有 schema, 并使用默认的 /api 前缀
    const allSchemas = await request.get<Record<string, JSONSchema>>('/ai/schemas')
    if (allSchemas) {
      const schemaMap = new Map<string, JSONSchema>(Object.entries(allSchemas))
      
      // 创建一个新的 Map 用于存储解引用后的 schema
      const dereferencedSchemaMap = new Map<string, JSONSchema>()

      // 第一步：先填充所有 schema 到 Map 中
      for (const [name, schema] of schemaMap.entries()) {
        dereferencedSchemaMap.set(name, schema);
      }
      
      // 第二步：遍历并解引用每一个 schema
      for (const [name, schema] of dereferencedSchemaMap.entries()) {
        dereferencedSchemaMap.set(name, dereferenceSchema(schema, dereferencedSchemaMap));
      }

      // DEBUG: Log all the schema keys that were loaded
      console.log('[SchemaService] All schema keys loaded from /ai/schemas:', Array.from(dereferencedSchemaMap.keys()));

      schemas.value = dereferencedSchemaMap
    }
  } catch (e) {
    console.error('Failed to load schemas from /ai/schemas:', e)
    error.value = e
  } finally {
    isLoading.value = false
  }
}

// 新增：强制刷新（清空缓存并重新加载）
async function refreshSchemas() {
  try {
    schemas.value = new Map()
    isLoading.value = false
    await loadSchemas()
  } catch (e) {
    console.error('Failed to refresh schemas:', e)
  }
}

/**
 * 获取 schema 的名称。
 * @param name schema 的名称 (例如, 'VolumeOutline').
 * @returns 如果找到则返回 JSONSchema，否则返回 undefined。
 */
function getSchema(name: string): JSONSchema | undefined {
  return schemas.value.get(name)
}

// --- 导出 ---
// 导出一个单例对象用于与 schema 交互。
export const schemaService = {
  schemas,
  isLoading,
  error,
  loadSchemas,
  refreshSchemas,
  getSchema
} 