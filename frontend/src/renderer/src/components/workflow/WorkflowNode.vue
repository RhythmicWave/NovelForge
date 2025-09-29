<script setup lang="ts">
import { computed, ref, onMounted, watch } from 'vue'
import { Handle, Position } from '@vue-flow/core'
import { NodeToolbar } from '@vue-flow/node-toolbar'
import { getCardTypes } from '@renderer/api/cards'
import { parseSchemaFields, getFieldIcon, type ParsedField } from '@renderer/services/schemaFieldParser'
import NodeFieldSelector from './NodeFieldSelector.vue'
import { 
  ArrowDown, ArrowUp, Setting, Delete, DocumentCopy,
  EditPen, Check, Close
} from '@element-plus/icons-vue'

const props = defineProps<{ 
  id: string 
  data: { 
    type: string
    params?: any
    toolbarVisible?: boolean
    expanded?: boolean
  } 
  selected?: boolean
}>()

// 不使用emit，改用DOM事件发射机制
// const emit = defineEmits<{...}>()

// 节点状态
const isExpanded = ref(props.data.expanded ?? false)

// Card.Read 节点的字段信息
const cardTypeFields = ref<ParsedField[]>([])

// 本地参数副本，用于实时编辑
const localParams = ref({ ...props.data.params })

// 节点配置
const nodeConfig = computed(() => {
  const type = props.data.type
  switch (type) {
    case 'Card.Read':
      return {
        title: 'Card.Read',
        color: '#409EFF',
        icon: '📖',
        primaryFields: ['target', 'type_name'],
        secondaryFields: ['fields'],
        contextHint: '读取卡片到 state.card'
      }
    case 'Card.UpsertChildByTitle':
      return {
        title: 'UpsertChild',
        color: '#67C23A',
        icon: '➕',
        primaryFields: ['cardType', 'title', 'contentTemplate'],
        secondaryFields: ['contentMerge', 'contentPath', 'useItemAsContent'],
        contextHint: '创建子卡片 (不影响 state.card)'
      }
    case 'Card.ModifyContent':
      return {
        title: 'ModifyContent',
        color: '#E6A23C',
        icon: '✏️',
        primaryFields: ['contentMerge', 'setPath', 'setValue'],
        secondaryFields: [],
        contextHint: '修改当前卡片 (state.card)'
      }
    case 'List.ForEach':
      return {
        title: 'ForEach',
        color: '#F56C6C',
        icon: '🔄',
        primaryFields: ['listPath'],
        secondaryFields: ['body']
      }
    case 'List.ForEachRange':
      return {
        title: 'ForEachRange',
        color: '#F56C6C',
        icon: '🔢',
        primaryFields: ['countPath', 'start'],
        secondaryFields: []
      }
    case 'Card.ClearFields':
      return {
        title: 'ClearFields',
        color: '#909399',
        icon: '🗑️',
        primaryFields: ['fields'],
        secondaryFields: []
      }
    default:
      return {
        title: type || 'Unknown',
        color: '#606266',
        icon: '⚙️',
        primaryFields: [],
        secondaryFields: []
      }
  }
})

// 计算节点摘要
const nodeSummary = computed(() => {
  const config = nodeConfig.value
  const params = localParams.value || {}
  const summaryParts: string[] = []
  
  // 根据主要字段生成摘要
  config.primaryFields.forEach(field => {
    const fieldValue = params[field]
    if (fieldValue !== undefined && fieldValue !== null && fieldValue !== '') {
      let value: string
      if (field === 'contentMerge' && typeof fieldValue === 'object') {
        // 特殊处理 contentMerge 对象，显示具体的键值对
        const obj = fieldValue
        const pairs = Object.entries(obj).map(([k, v]) => {
          if (Array.isArray(v) && v.length === 0) {
            return `${k}:[]`
          } else if (typeof v === 'string') {
            return `${k}:"${v}"`
          } else {
            return `${k}:${JSON.stringify(v)}`
          }
        })
        if (pairs.length > 0) {
          value = `合并: {${pairs.join(', ')}}`
        } else {
          value = '合并: {}'
        }
      } else if (field === 'title' && typeof fieldValue === 'string' && fieldValue.includes('{')) {
        // 特殊处理模板字符串，简化显示
        const simplified = fieldValue.replace(/\{[^}]+\}/g, (match) => {
          if (match.includes('.')) {
            const parts = match.slice(1, -1).split('.')
            return `{${parts[parts.length - 1]}}`
          }
          return match
        })
        value = simplified
      } else if (field === 'contentTemplate' && typeof fieldValue === 'object') {
        // 特殊处理 contentTemplate 对象，显示关键字段
        const obj = fieldValue
        const keyFields = ['volume_number', 'stage_number', 'chapter_number', 'title']
        const relevantKeys = Object.keys(obj).filter(k => keyFields.includes(k))
        if (relevantKeys.length > 0) {
          value = `模板: {${relevantKeys.join(', ')}}`
        } else {
          value = `模板: {${Object.keys(obj).length}字段}`
        }
      } else if (field === 'cardType') {
        // 卡片类型直接显示
        value = String(fieldValue)
      } else {
        value = String(fieldValue)
      }
      
      if (value.length > 25) {
        summaryParts.push(`${value.slice(0, 22)}...`)
      } else {
        summaryParts.push(value)
      }
    }
  })
  
  return summaryParts.join(' · ')
})

// 字段编辑器组件
const getFieldEditor = (field: string, value: any) => {
  const config = nodeConfig.value
  
  // 根据字段类型返回不同的编辑器配置
  if (field === 'target' && config.title === 'Card.Read') {
    return {
      type: 'select' as const,
      options: [
        { label: 'Current ($self)', value: '$self', desc: '读取当前卡片' },
        { label: 'Parent ($parent)', value: '$parent', desc: '读取父级卡片' }
      ],
      required: true,
      description: '指定要读取的卡片目标'
    }
  }
  
  if (field === 'type_name') {
    return {
      type: 'select' as const,
      options: cardTypeFields.value.map(f => ({ 
        label: f.title || f.name, 
        value: f.name,
        desc: `${f.name}类型的卡片`
      })),
      description: '指定要读取的卡片类型'
    }
  }
  
  if (field === 'cardType') {
    return {
      type: 'select' as const, 
      options: cardTypeFields.value.map(f => ({
        label: f.title || f.name,
        value: f.name,
        desc: `${f.name}卡片`
      })),
      required: true,
      description: '要创建的子卡片类型'
    }
  }
  
  if (field === 'title') {
    return {
      type: 'input' as const,
      placeholder: '如：第{item.chapter_number}章 或 {item.name}',
      description: '子卡片的标题模板，支持变量替换'
    }
  }
  
  if (field === 'listPath') {
    return {
      type: 'input' as const,
      placeholder: '如：$.content.chapter_outline_list',
      description: 'JSONPath表达式，指向要遍历的数组字段'
    }
  }
  
  if (field === 'contentMerge') {
    return {
      type: 'textarea' as const,
      placeholder: '{"field1": "value1", "field2": []}',
      description: 'JSON格式的内容合并对象'
    }
  }
  
  if (field === 'contentTemplate') {
    return {
      type: 'textarea' as const,
      placeholder: '{"volume_number": "{$.content.volume_number}", "title": "{item.title}"}',
      description: 'JSON格式的内容模板对象'
    }
  }
  
  if (field === 'countPath') {
    return {
      type: 'input' as const,
      placeholder: '如：$.content.volume_count',
      description: 'JSONPath表达式，指向表示数量的字段'
    }
  }
  
  if (field === 'start') {
    return {
      type: 'number' as const,
      placeholder: '起始值，通常为1',
      description: '遍历的起始数字'
    }
  }
  
  return {
    type: 'input' as const,
    placeholder: `请输入 ${field}`
  }
}

// 次要字段编辑器配置
const getSecondaryFieldEditor = (field: string, value: any) => {
  if (field === 'contentMerge') {
    return {
      type: 'textarea' as const,
      placeholder: '如：{"status": "completed", "updated_at": "$now"}',
      description: 'JSON对象，要合并到卡片内容的数据'
    }
  }
  
  if (field === 'contentTemplate') {
    return {
      type: 'textarea' as const,
      placeholder: '{"volume_number": "{$.content.volume_number}", "title": "{item.title}"}',
      description: 'JSON格式的内容模板对象'
    }
  }
  
  if (field === 'contentPath') {
    return {
      type: 'input' as const,
      placeholder: '如：$.content.description',
      description: 'JSONPath表达式，从源数据提取内容'
    }
  }
  
  if (field === 'useItemAsContent') {
    return {
      type: 'switch' as const,
      description: '是否直接将遍历的item作为卡片内容'
    }
  }
  
  if (field === 'setPath') {
    return {
      type: 'input' as const,
      placeholder: '如：$.content.status',
      description: 'JSONPath表达式，指定要设置的字段路径'
    }
  }
  
  if (field === 'setValue') {
    return {
      type: 'input' as const,
      placeholder: '要设置的值',
      description: '要写入指定路径的数据'
    }
  }
  
  if (field === 'fields') {
    return {
      type: 'textarea' as const,
      placeholder: '["$.content.field1", "$.content.field2"]',
      description: 'JSON数组，指定要清空的字段路径列表'
    }
  }
  
  return {
    type: 'textarea' as const,
    placeholder: `请输入 ${field}`
  }
}

// 这些编辑函数已被 NodeFieldSelector 组件替代，不再需要

// 更新参数
const updateParam = (key: string, value: any) => {
  localParams.value = { ...localParams.value, [key]: value }
  
  // 发射DOM事件
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('update-params', {
      detail: { nodeId: props.id, params: localParams.value }
    }))
  }
}

// 切换展开状态
const toggleExpanded = () => {
  isExpanded.value = !isExpanded.value
  
  // 发射DOM事件
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('update-expanded', {
      detail: { nodeId: props.id, expanded: isExpanded.value }
    }))
  }
}

// 删除节点
const deleteNode = () => {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('delete-node', {
      detail: { nodeId: props.id }
    }))
  }
}

// 获取Card类型数据
const loadCardTypes = async () => {
  try {
    const types = await getCardTypes()
    cardTypeFields.value = types.map(t => ({
      name: t.name,
      title: t.name,
      type: 'object',
      path: t.name,
      description: '',
      required: false,
      expanded: false,
      expandable: false
    }))
  } catch (e) {
    console.warn('获取卡片类型失败:', e)
  }
}

// 监听参数变化，同步本地状态
watch(() => props.data.params, (newParams) => {
  localParams.value = { ...newParams }
}, { deep: true })

watch(() => props.data.expanded, (expanded) => {
  isExpanded.value = expanded ?? false
})

onMounted(() => {
  loadCardTypes()
})
</script>

<template>
  <div
    class="workflow-node"
    :class="{
      'node-selected': selected,
      'node-expanded': isExpanded
    }"
    :style="{ '--node-color': nodeConfig.color }"
  >
    <!-- Handles -->
    <Handle id="t" type="target" :position="Position.Top" class="node-handle" />
    <Handle id="l" type="target" :position="Position.Left" class="node-handle" />
    <Handle id="r" type="source" :position="Position.Right" class="node-handle" />
    <Handle id="b" type="source" :position="Position.Bottom" class="node-handle" />
    
    <!-- Node Toolbar -->
    <NodeToolbar :is-visible="!!props.data?.toolbarVisible" :position="Position.Top">
      <div class="node-toolbar">
        <el-button size="small" @click="toggleExpanded" :icon="isExpanded ? ArrowUp : ArrowDown">
          {{ isExpanded ? '收起' : '展开' }}
        </el-button>
        <el-button size="small" @click="deleteNode" :icon="Delete" type="danger">删除</el-button>
      </div>
    </NodeToolbar>

    <!-- Node Header -->
    <div class="node-header">
      <div class="node-icon">{{ nodeConfig.icon }}</div>
      <div class="node-title">
        <div class="node-type">{{ nodeConfig.title }}</div>
        <div class="node-summary" v-if="nodeSummary">{{ nodeSummary }}</div>
        <div class="node-context-hint" v-if="nodeConfig.contextHint">{{ nodeConfig.contextHint }}</div>
        </div>
      <div class="node-actions">
        <el-button 
          text 
          size="small" 
          :icon="isExpanded ? ArrowUp : ArrowDown"
          @click="toggleExpanded"
          class="expand-btn"
        />
      </div>
    </div>
    
    <!-- Primary Fields (Always Visible) -->
    <div class="node-fields primary-fields">
      <NodeFieldSelector
        v-for="field in nodeConfig.primaryFields"
        :key="field"
        :field-key="field"
        :field-value="localParams[field]"
        :field-config="getFieldEditor(field, localParams[field])"
        class="primary-field-selector"
        @update:value="(value) => updateParam(field, value)"
      />
    </div>

    <!-- Secondary Fields (Expandable) -->
    <div v-if="isExpanded" class="node-fields secondary-fields">
      <div class="fields-divider"></div>
      <NodeFieldSelector
        v-for="field in nodeConfig.secondaryFields"
        :key="field"
        :field-key="field"
        :field-value="localParams[field]"
        :field-config="getSecondaryFieldEditor(field, localParams[field])"
        class="secondary-field-selector"
        @update:value="(value) => updateParam(field, value)"
      />
    </div>

    <!-- Card.Read 字段结构预览 -->
    <div 
      v-if="isExpanded && nodeConfig.title === 'Card.Read' && localParams.type_name" 
      class="node-schema-preview"
    >
      <div class="schema-title">字段结构</div>
      <div class="schema-hint">此卡片类型包含的主要字段</div>
    </div>
  </div>
</template>

<style scoped>
.workflow-node {
  background: var(--el-bg-color); 
  border: 2px solid var(--el-border-color);
  border-radius: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  width: 260px;
  min-height: 100px;
  position: relative;
  transition: all 0.3s ease;
}

.workflow-node:hover {
  border-color: var(--node-color, var(--el-color-primary));
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.15);
}

.node-selected {
  border-color: var(--node-color, var(--el-color-primary)) !important;
  box-shadow: 0 0 0 3px rgba(64, 158, 255, 0.2);
}

.node-expanded {
  width: 300px;
}

/* 移除了 node-editing 状态，现在由 NodeFieldSelector 处理编辑 */

/* Handles */
.node-handle {
  width: 12px;
  height: 12px;
  border: 2px solid var(--node-color, var(--el-color-primary));
  background: var(--el-bg-color);
  transition: all 0.2s ease;
}

.node-handle:hover {
  width: 16px;
  height: 16px;
  border-width: 3px;
}

/* Header */
.node-header {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background: linear-gradient(135deg, var(--node-color, var(--el-color-primary))22, transparent);
}

.node-icon {
  font-size: 20px;
  margin-right: 8px;
  flex-shrink: 0;
}

.node-title {
  flex: 1;
  min-width: 0;
}

.node-type {
  font-weight: 600;
  font-size: 14px;
  color: var(--el-text-color-primary);
  margin-bottom: 2px;
}

.node-summary {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.node-context-hint {
  font-size: 10px;
  color: var(--el-color-info);
  font-style: italic;
  margin-top: 2px;
  opacity: 0.8;
}

.node-actions {
  flex-shrink: 0;
}

.expand-btn {
  width: 24px !important;
  height: 24px !important;
  border-radius: 50%;
}

/* Fields */
.node-fields {
  padding: 8px 16px;
}

.secondary-fields {
  background: var(--el-fill-color-extra-light);
  border-radius: 0 0 10px 10px;
}

.fields-divider {
  height: 1px;
  background: var(--el-border-color-lighter);
  margin: 8px -16px 12px;
}

/* 移除了手动编辑器相关的样式，现在使用 NodeFieldSelector 组件 */

/* Field Selectors */
.primary-field-selector {
  margin-bottom: 8px;
}

.secondary-field-selector {
  margin-bottom: 10px;
}

/* 为 NodeFieldSelector 组件提供特定样式 */
:deep(.node-field-selector) {
  margin-bottom: 6px;
}

:deep(.node-field-selector .field-label) {
  font-size: 11px;
  font-weight: 500;
  color: var(--el-text-color-regular);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

/* Node Toolbar */
.node-toolbar {
  display: flex;
  gap: 4px;
  background: var(--el-bg-color);
  padding: 6px;
  border-radius: 6px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

/* Schema Preview */
.node-schema-preview {
  padding: 8px 16px;
  border-top: 1px solid var(--el-border-color-lighter);
  background: var(--el-fill-color-extra-light);
}

.schema-title {
  font-size: 10px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  text-transform: uppercase;
  margin-bottom: 4px;
}

.schema-hint {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  font-style: italic;
}

/* 响应式调整 */
@media (max-width: 1200px) {
  .workflow-node {
    width: 220px;
  }
  
  .node-expanded {
    width: 260px;
  }
}
</style>
