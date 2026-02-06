/**
 * 节点编辑器 Composable
 * 
 * 提取节点编辑的核心逻辑，包括：
 * - 代码解析
 * - 代码生成
 * - 节点管理
 */

import { ref, Ref } from 'vue'
import request from '@/api/request'
import { ElMessage } from 'element-plus'

export interface WorkflowNode {
  variable: string
  nodeType: string
  category: string
  code: string
  isAsync?: boolean  // 是否异步执行
  fields: Array<{
    name: string
    type: string
    value: any
    label?: string
    description?: string
    default?: any
    required?: boolean
    minimum?: number
    maximum?: number
    component?: string  // x-component 扩展
  }>
  outputs?: Array<{
    name: string
    label: string
  }>
  collapsed?: boolean
  disabled?: boolean  // 节点是否被禁用
}

export function useNodeEditor(initialCode: Ref<string>) {
  const nodes = ref<WorkflowNode[]>([])
  const selectedIndex = ref(-1)
  const isInternalUpdate = ref(false)

  /**
   * 解析代码为节点列表
   */
  async function parseCodeToNodes(code: string): Promise<WorkflowNode[]> {
    if (!code || !code.trim()) {
      console.log('[parseCodeToNodes] 代码为空')
      return []
    }

    try {
      console.log('[parseCodeToNodes] 开始解析代码...')
      
      // 1. 分离启用和禁用的代码
      const lines = code.split('\n')
      const enabledLines: string[] = []
      const disabledLines: { line: string, originalCode: string }[] = []
      
      for (const line of lines) {
        const trimmed = line.trim()
        if (trimmed.startsWith('# DISABLED:')) {
          // 提取被禁用的原始代码
          const originalCode = trimmed.substring('# DISABLED:'.length).trim()
          disabledLines.push({ line, originalCode })
        } else {
          enabledLines.push(line)
        }
      }
      
      // 2. 解析启用的节点
      const enabledCode = enabledLines.join('\n')
      const response: any = await request.post('/workflows/parse', { code: enabledCode }, '/api')
      
      if (!response.statements || response.statements.length === 0) {
        console.log('[parseCodeToNodes] 解析结果为空')
        return []
      }

      const parsedNodes: WorkflowNode[] = []

      for (const stmt of response.statements) {
        try {
          const nodeType = stmt.node_type
          const variable = stmt.variable

          // 获取节点元数据
          const metadata: any = await request.get(`/nodes/${nodeType}/metadata`, {}, '/api')
          
          const node: WorkflowNode = {
            variable,
            nodeType,
            category: metadata.category || 'Unknown',
            code: stmt.code,
            isAsync: stmt.is_async || false,  // 从解析结果中获取
            disabled: stmt.disabled || false,  // 从解析结果中获取（元数据）
            fields: [],
            outputs: metadata.outputs || [],
            collapsed: false
          }

          // 构建字段列表 - 优先使用 input_schema（新格式），回退到 config_model（旧格式）
          const schema = metadata.input_schema || metadata.config_model
          if (schema?.properties) {
            for (const [fieldName, fieldSchema] of Object.entries(schema.properties)) {
              const fieldDef = fieldSchema as any
              node.fields.push({
                name: fieldName,
                type: fieldDef.type || 'string',
                value: stmt.config?.[fieldName],
                label: fieldDef.title || fieldName,
                description: fieldDef.description,
                default: fieldDef.default,
                required: schema.required?.includes(fieldName),
                // 字段约束
                minimum: fieldDef.minimum,
                maximum: fieldDef.maximum,
                // x-component 扩展
                component: fieldDef['x-component']
              })
            }
          }

          parsedNodes.push(node)
        } catch (error) {
          console.error(`[parseCodeToNodes] 解析节点失败:`, error)
          ElMessage.error(`解析节点 ${stmt.variable} 失败`)
        }
      }

      // 3. 解析禁用的节点
      for (const { originalCode } of disabledLines) {
        try {
          // 解析单行禁用代码
          const disabledResponse: any = await request.post('/workflows/parse', { code: originalCode }, '/api')
          
          if (disabledResponse.statements && disabledResponse.statements.length > 0) {
            const stmt = disabledResponse.statements[0]
            const nodeType = stmt.node_type
            const variable = stmt.variable

            // 获取节点元数据
            const metadata: any = await request.get(`/nodes/${nodeType}/metadata`, {}, '/api')
            
            const node: WorkflowNode = {
              variable,
              nodeType,
              category: metadata.category || 'Unknown',
              code: originalCode,
              isAsync: stmt.is_async || false,  // 从解析结果中获取
              fields: [],
              outputs: metadata.outputs || [],
              collapsed: false,
              disabled: true  // 标记为禁用
            }

            // 构建字段列表 - 优先使用 input_schema（新格式），回退到 config_model（旧格式）
            const schema = metadata.input_schema || metadata.config_model
            if (schema?.properties) {
              for (const [fieldName, fieldSchema] of Object.entries(schema.properties)) {
                const fieldDef = fieldSchema as any
                node.fields.push({
                  name: fieldName,
                  type: fieldDef.type || 'string',
                  value: stmt.config?.[fieldName],
                  label: fieldDef.title || fieldName,
                  description: fieldDef.description,
                  default: fieldDef.default,
                  required: schema.required?.includes(fieldName),
                  // 字段约束
                  minimum: fieldDef.minimum,
                  maximum: fieldDef.maximum,
                  // x-component 扩展
                  component: fieldDef['x-component']
                })
              }
            }
                  default: schema.default
                })
              }
            }

            parsedNodes.push(node)
          }
        } catch (error) {
          console.error(`[parseCodeToNodes] 解析禁用节点失败:`, error)
          // 禁用节点解析失败不影响整体流程
        }
      }

      console.log('[parseCodeToNodes] 解析完成，节点数:', parsedNodes.length)
      return parsedNodes
    } catch (error: any) {
      console.error('[parseCodeToNodes] 代码解析失败:', error)
      ElMessage.error(`代码解析失败：${error.message || error}`)
      return []
    }
  }

  /**
   * 将节点列表转换为代码
   * 禁用的节点会添加元数据注释
   */
  function nodesToCode(): string {
    const codes = nodes.value
      .filter(node => node.code && node.code.trim())
      .map(node => {
        if (node.disabled) {
          // 禁用的节点：添加元数据注释
          return `# @meta: disabled=true\n${node.code}`
        }
        return node.code
      })
    
    const result = codes.join('\n')
    console.log('[nodesToCode] 生成代码，节点数:', nodes.value.length, '有效代码行数:', codes.length)
    return result
  }

  /**
   * 添加节点
   */
  function addNode(node: WorkflowNode) {
    nodes.value.push(node)
  }

  /**
   * 删除节点
   */
  function deleteNode(index: number) {
    nodes.value.splice(index, 1)
    if (selectedIndex.value === index) {
      selectedIndex.value = -1
    } else if (selectedIndex.value > index) {
      selectedIndex.value--
    }
  }

  /**
   * 选择节点
   */
  function selectNode(index: number) {
    selectedIndex.value = index
  }

  /**
   * 更新节点代码
   */
  function updateNodeCode(index: number, newCode: string) {
    if (index >= 0 && index < nodes.value.length) {
      nodes.value[index].code = newCode
    }
  }

  /**
   * 切换节点禁用状态
   */
  function toggleNodeDisabled(index: number) {
    if (index >= 0 && index < nodes.value.length) {
      const node = nodes.value[index]
      node.disabled = !node.disabled
      console.log(`[toggleNodeDisabled] 节点 ${node.variable} 禁用状态: ${node.disabled}`)
    }
  }

  return {
    nodes,
    selectedIndex,
    isInternalUpdate,
    parseCodeToNodes,
    nodesToCode,
    addNode,
    deleteNode,
    selectNode,
    updateNodeCode,
    toggleNodeDisabled
  }
}
