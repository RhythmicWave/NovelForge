/**
 * 指令执行器
 * 
 * 负责将后端发送的指令应用到数据对象。
 * 所有校验已在后端完成，这里只负责机械地执行指令。
 */

import { set, get } from 'lodash-es'
import type { Instruction } from '@renderer/types/instruction'

/**
 * 指令执行器类
 */
export class InstructionExecutor {
  private data: Record<string, any> = {}

  /**
   * 创建执行器
   * @param initialData 初始数据
   */
  constructor(initialData: Record<string, any> = {}) {
    this.data = { ...initialData }
  }

  /**
   * 执行单条指令
   * @param instruction 指令对象
   */
  execute(instruction: Instruction): void {
    switch (instruction.op) {
      case 'set':
        this.executeSet(instruction.path, instruction.value)
        break
      case 'append':
        this.executeAppend(instruction.path, instruction.value)
        break
      case 'done':
        // done 指令无需执行
        break
    }
  }

  /**
   * 执行 set 指令
   * @param path JSON Pointer 路径
   * @param value 要设置的值
   */
  private executeSet(path: string, value: any): void {
    const lodashPath = this.convertPath(path)
    set(this.data, lodashPath, value)
  }

  /**
   * 执行 append 指令
   * @param path JSON Pointer 路径
   * @param value 要追加的元素
   */
  private executeAppend(path: string, value: any): void {
    const lodashPath = this.convertPath(path)
    const arr = get(this.data, lodashPath) || []
    
    if (!Array.isArray(arr)) {
      console.warn(`路径 ${path} 不是数组，无法执行 append 操作`)
      return
    }
    
    arr.push(value)
    set(this.data, lodashPath, arr)
  }

  /**
   * 将 JSON Pointer 路径转换为 lodash 路径
   * @param pointer JSON Pointer 格式（如 /name 或 /config/theme）
   * @returns lodash 路径格式（如 name 或 config.theme）
   */
  private convertPath(pointer: string): string {
    // 移除开头的 /
    if (pointer.startsWith('/')) {
      pointer = pointer.slice(1)
    }
    
    // 将 / 替换为 .
    return pointer.replace(/\//g, '.')
  }

  /**
   * 获取当前数据
   * @returns 数据对象
   */
  getData(): Record<string, any> {
    return this.data
  }

  /**
   * 重置数据
   * @param newData 新数据
   */
  reset(newData: Record<string, any> = {}): void {
    this.data = { ...newData }
  }

  /**
   * 清空数据
   */
  clear(): void {
    this.data = {}
  }
}
