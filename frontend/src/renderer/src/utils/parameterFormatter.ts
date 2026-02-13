/**
 * 参数值格式化工具
 * 
 * 统一处理工作流节点参数的格式化逻辑
 */

export interface ParameterFormatOptions {
  type: string // 参数类型：string, integer, number, boolean, etc.
  value: any   // 原始值
}

export class ParameterFormatter {
  private static escapeString(value: any): string {
    const text = String(value)
    return text
      .replace(/\\/g, '\\\\')
      .replace(/\r/g, '\\r')
      .replace(/\n/g, '\\n')
      .replace(/\t/g, '\\t')
      .replace(/"/g, '\\"')
  }
  /**
   * 检测是否是变量引用
   * 格式：变量名.属性名 (例如: text.content, novel.chapter_list)
   */
  static isVariableReference(value: any): boolean {
    if (value === null || value === undefined) return false
    const strValue = String(value)
    return /^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)+$/.test(strValue)
  }

  /**
   * 检测值是否为空
   * 注意：0 和 false 不算空值
   */
  static isEmpty(value: any): boolean {
    if (value === 0 || value === false) return false
    if (value === null || value === undefined) return true
    
    const strValue = String(value).trim()
    return strValue === ''
  }

  /**
   * 格式化参数值为 Python 代码
   */
  static format(options: ParameterFormatOptions): string {
    const { type, value } = options

    // 空值处理
    if (this.isEmpty(value)) {
      return ''
    }

    // 变量引用：直接使用（解析器会自动添加 $ 标记）
    if (this.isVariableReference(value)) {
      return String(value)
    }

    // 根据类型格式化
    let result: string
    switch (type) {
      case 'integer':
      case 'number':
        result = String(value)
        break

      case 'boolean':
        // 转换为 Python 布尔值
        result = (value === 'true' || value === true) ? 'True' : 'False'
        break

      case 'string':
        // 字符串：加引号，转义特殊字符
        result = `"${this.escapeString(value)}"`
        break

      case 'array':
        // 数组类型：支持数组或逗号分隔的字符串
        if (Array.isArray(value)) {
          // 直接是数组
          const items = value.map(item => `"${this.escapeString(item)}"`)
          result = `[${items.join(', ')}]`
        } else if (typeof value === 'string') {
          // 逗号分隔的字符串，转换为数组
          const items = value.split(',').map(item => item.trim()).filter(item => item)
          result = `[${items.map(item => `"${this.escapeString(item)}"`).join(', ')}]`
        } else {
          result = this.formatComplexType(value)
        }
        break
      
      case 'object':
        // 复杂类型：JSON 序列化（需要转换为 Python 格式）
        result = this.formatComplexType(value)
        break

      default:
        // 未知类型：检查是否是对象
        if (typeof value === 'object' && value !== null) {
          result = this.formatComplexType(value)
        } else {
          // 默认当作字符串处理
          result = `"${this.escapeString(value)}"`
        }
        break
    }
    
    // 最终安全检查：确保返回字符串
    if (typeof result !== 'string') {
      console.error('[ParameterFormatter.format] 结果不是字符串！强制转换:', result)
      result = JSON.stringify(result)
    }
    
    return result
  }

  /**
   * 格式化复杂类型（数组、对象）
   */
  private static formatComplexType(value: any): string {
    if (Array.isArray(value)) {
      const items = value.map(item => {
        // 递归格式化数组元素
        if (typeof item === 'object' && item !== null) {
          return this.formatComplexType(item)
        } else if (typeof item === 'string') {
          return `"${this.escapeString(item)}"`
        } else if (typeof item === 'number') {
          return String(item)
        } else if (typeof item === 'boolean') {
          return item ? 'True' : 'False'
        } else {
          return `"${this.escapeString(item)}"`
        }
      })
      return `[${items.join(', ')}]`
    }

    if (typeof value === 'object' && value !== null) {
      const pairs = Object.entries(value).map(([key, val]) => {
        // 递归格式化对象值
        let formattedVal: string
        if (typeof val === 'object' && val !== null) {
          formattedVal = this.formatComplexType(val)
        } else if (typeof val === 'string') {
          formattedVal = `"${this.escapeString(val)}"`
        } else if (typeof val === 'number') {
          formattedVal = String(val)
        } else if (typeof val === 'boolean') {
          formattedVal = val ? 'True' : 'False'
        } else {
          formattedVal = `"${this.escapeString(val)}"`
        }
        return `"${key}": ${formattedVal}`
      })
      return `{${pairs.join(', ')}}`
    }

    return String(value)
  }

  /**
   * 解析显示值（去掉引号）
   */
  static parseDisplayValue(value: any): string {
    if (value === null || value === undefined) return ''

    // 处理对象类型（字典）
    if (typeof value === 'object' && !Array.isArray(value)) {
      try {
        // 转换为 Python 字典格式
        return this.formatComplexType(value)
      } catch (e) {
        return JSON.stringify(value)
      }
    }

    // 处理数组类型
    if (Array.isArray(value)) {
      try {
        return this.formatComplexType(value)
      } catch (e) {
        return JSON.stringify(value)
      }
    }

    let strValue = String(value)

    // 去掉字符串引号
    if ((strValue.startsWith('"') && strValue.endsWith('"')) ||
        (strValue.startsWith("'") && strValue.endsWith("'"))) {
      return strValue.substring(1, strValue.length - 1)
    }

    return strValue
  }
}
