<template>
  <div class="property-panel">
    <div class="panel-header">
      <h3>{{ selectedNode ? '节点属性' : '未选中节点' }}</h3>
    </div>

    <div v-if="selectedNode" class="panel-content">
      <el-scrollbar>
        <el-tabs v-model="activeTab">
          <!-- 基本属性 -->
          <el-tab-pane label="属性" name="properties">
            <div class="properties-section">
              <!-- 节点ID -->
              <div class="property-item">
                <label>节点ID</label>
                <el-input :model-value="selectedNode.id" disabled size="small" />
              </div>

              <!-- 节点类型 -->
              <div class="property-item">
                <label>节点类型</label>
                <el-input :model-value="selectedNode.type" disabled size="small" />
              </div>

              <!-- 节点标签 -->
              <div class="property-item">
                <label>标签</label>
                <el-input
                  :model-value="selectedNode.data?.label"
                  @input="updateLabel"
                  size="small"
                  placeholder="输入节点标签"
                />
              </div>

              <!-- 节点描述 -->
              <div class="property-item">
                <label>描述</label>
                <el-input
                  :model-value="selectedNode.data?.description"
                  @input="updateDescription"
                  type="textarea"
                  :rows="2"
                  size="small"
                  placeholder="输入节点描述"
                />
              </div>

              <!-- 触发器输出变量提示 (仅Trigger节点) -->
              <div v-if="selectedNode.type.startsWith('Trigger.') && nodeDefinition?.outputs?.length" class="property-item">
                <el-divider>可用输出变量</el-divider>
                <div class="trigger-outputs">
                  <div class="trigger-output-desc">
                    以下变量已注入全局上下文，可直接连线或使用 <code>{variable}</code> 引用：
                  </div>
                  <div v-for="out in nodeDefinition.outputs" :key="out.name" class="output-var-item">
                    <el-tag size="small" effect="dark" type="info">{{ out.name }}</el-tag>
                    <span class="output-var-desc">{{ out.description }}</span>
                  </div>
                </div>
              </div>

              <!-- 节点配置（动态 - 基于 JSON Schema） -->
              <div v-if="schemaProperties.length > 0" class="property-item">
                <el-divider>节点配置</el-divider>
                <div v-for="prop in schemaProperties" :key="prop.name" class="config-item">
                  <div class="config-label">
                    <span>{{ prop.title || prop.name }}</span>
                    <el-tag v-if="prop.required" size="small" type="danger" effect="plain" class="required-tag">必填</el-tag>
                    <el-tooltip v-if="prop.description" :content="prop.description" placement="top">
                      <el-icon class="info-icon"><InfoFilled /></el-icon>
                    </el-tooltip>
                  </div>
                  
                  <!-- 枚举选择 -->
                  <div v-if="prop.enum" class="input-wrapper">
                    <el-select
                      :model-value="getConfigValue(prop.name, prop.default)"
                      @change="(val) => updateConfig(prop.name, val)"
                      size="small"
                      style="width: 100%"
                      :placeholder="getPlaceholder(prop)"
                    >
                      <el-option
                        v-for="opt in prop.enum"
                        :key="opt"
                        :label="opt"
                        :value="opt"
                      />
                    </el-select>
                    <div v-if="isInputConnected(prop.name)" class="connection-hint">
                      <el-icon><Connection /></el-icon>
                      已有连线提供默认值
                    </div>
                  </div>
                  
                  
                  <!-- 布尔值开关 -->
                  <PropertyFieldWrapper v-else-if="prop.type === 'boolean'" :show-connection-hint="isInputConnected(prop.name)">
                    <el-switch
                      :model-value="getConfigValue(prop.name, prop.default)"
                      @change="(val) => updateConfig(prop.name, val)"
                    />
                  </PropertyFieldWrapper>
                  
                  <!-- 数字输入 -->
                  <PropertyFieldWrapper v-else-if="prop.type === 'integer' || prop.type === 'number'" :show-connection-hint="isInputConnected(prop.name)">
                    <el-input-number
                      :model-value="getConfigValue(prop.name, prop.default)"
                      @input="(val) => updateConfig(prop.name, val)"
                      size="small"
                      style="width: 100%"
                      :placeholder="getPlaceholder(prop)"
                    />
                  </PropertyFieldWrapper>
                  
                  <!-- 卡片类型选择 -->
                  <PropertyFieldWrapper v-else-if="prop.name === 'card_type' || (prop.name === 'cardType' && prop.type === 'string')" :show-connection-hint="isInputConnected(prop.name)">
                    <el-select
                      :model-value="getConfigValue(prop.name, prop.default)"
                      @change="(val) => updateConfig(prop.name, val)"
                      size="small"
                      style="width: 100%"
                      :placeholder="getPlaceholder(prop) || '选择卡片类型 (留空则监听所有)'"
                      filterable
                      clearable
                    >
                      <el-option label="所有类型 (监听全部)" :value="null" />
                      <el-option
                        v-for="ct in workflowStore.cardTypes"
                        :key="ct.id"
                        :label="ct.name"
                        :value="ct.name"
                      />
                    </el-select>
                  </PropertyFieldWrapper>

                  <!-- 文本域 / 模版输入 -->
                  <PropertyFieldWrapper v-else-if="prop.type === 'string' && (prop.name === 'content' || prop.name.includes('description') || prop.name === 'prompt' || prop.name.includes('template') || prop.name === 'condition')" :show-connection-hint="isInputConnected(prop.name)">
                    <TemplateInput
                      :model-value="getConfigValue(prop.name, prop.default)"
                      @update:model-value="(val) => updateConfig(prop.name, val)"
                      :rows="4"
                      :placeholder="getPlaceholder(prop)"
                      :variables="getVariables(prop.name)"
                    />
                  </PropertyFieldWrapper>

                  <!-- Generic Schema Field (for Object/Array/Complex types) -->
                  <PropertyFieldWrapper v-else-if="prop.type === 'object' || prop.type === 'array' || prop.name === 'filter_config'" :show-connection-hint="isInputConnected(prop.name)">
                    <SchemaField
                      :model-value="getConfigValue(prop.name, prop.default)"
                      @update:model-value="(val) => updateConfig(prop.name, val)"
                      :schema="prop.rawSchema"
                      :root-schema="nodeDefinition?.config_schema"
                    />
                  </PropertyFieldWrapper>
                  
                  <!-- 对象/数组 (显示格式化JSON) -->
                  <el-input
                    v-else-if="isObjectOrArray(getConfigValue(prop.name, prop.default))"
                    :model-value="formatValue(getConfigValue(prop.name, prop.default))"
                    @input="(val) => updateConfigFromJSON(prop.name, val)"
                    type="textarea"
                    :rows="6"
                    size="small"
                    :placeholder="prop.description || 'JSON格式'"
                  />
                  
                  <!-- 默认文本输入 -->
                  <PropertyFieldWrapper v-else :show-connection-hint="isInputConnected(prop.name)">
                    <el-input
                      :model-value="getConfigValue(prop.name, prop.default)"
                      @input="(val) => updateConfig(prop.name, val)"
                      size="small"
                      :placeholder="getPlaceholder(prop)"
                    />
                  </PropertyFieldWrapper>
                </div>
              </div>
              
              <!-- 没有配置项时的提示 -->
              <div v-else class="property-item empty-config">
                <span class="text-secondary">此节点无需额外配置</span>
              </div>

              <!-- 操作按钮 -->
              <div class="property-actions">
                <el-button @click="handleDelete" type="danger" size="small" plain>
                  <el-icon><Delete /></el-icon>
                  删除节点
                </el-button>
              </div>
            </div>
          </el-tab-pane>

          <!-- 运行结果 (合并 Log, Output, Debug) -->
          <el-tab-pane label="运行结果" name="result">
            <div class="result-section">
              <!-- 1. 输出预览 (优先显示) -->
              <div class="result-block" v-if="nodeOutputDisplay">
                <h4><el-icon><Monitor /></el-icon> 输出内容</h4>
                <div v-if="nodeOutputDisplay.type === 'json'" class="output-json">
                  <pre>{{ nodeOutputDisplay.content }}</pre>
                </div>
                <div v-else class="output-text">
                  <pre>{{ nodeOutputDisplay.content }}</pre>
                </div>
              </div>

              <!-- 2. 执行日志 -->
              <div class="result-block">
                <h4><el-icon><List /></el-icon> 执行日志</h4>
                <div v-if="nodeLogs.length === 0" class="empty-state">
                  暂无日志
                </div>
                <div v-else class="log-list">
                  <div v-for="(log, index) in nodeLogs" :key="index" class="log-item">
                    <span class="log-time">{{ log.time }}</span>
                    <span :class="['log-level', `level-${log.level}`]">{{ log.level }}</span>
                    <span class="log-message">{{ log.message }}</span>
                  </div>
                </div>
              </div>
              
              <el-divider />

              <!-- 3. 调试信息 (折叠) -->
              <el-collapse>
                <el-collapse-item title="调试信息 (Debug Info)" name="debug">
                  <div class="debug-content">
                    <h5>输入数据</h5>
                    <pre class="debug-data">{{ JSON.stringify(selectedNode.data?.inputs || {}, null, 2) }}</pre>
                    
                    <h5>输出数据</h5>
                    <pre class="debug-data">{{ JSON.stringify(selectedNode.data?.outputs || {}, null, 2) }}</pre>
                    
                    <h5>完整节点状态</h5>
                    <pre class="debug-data">{{ JSON.stringify(selectedNode, null, 2) }}</pre>
                  </div>
                </el-collapse-item>
              </el-collapse>
            </div>
          </el-tab-pane>
        </el-tabs>
      </el-scrollbar>
    </div>

    <div v-else class="panel-empty">
      <el-empty description="请选择一个节点" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Delete, InfoFilled, Monitor, List, Connection, Plus } from '@element-plus/icons-vue'
import { useWorkflowStore } from '@/stores/useWorkflowStore'
import SchemaField from '@/components/workflow-v2/schema/SchemaField.vue'
import PropertyFieldWrapper from '@/components/workflow-v2/panels/PropertyFieldWrapper.vue'
import TemplateInput from '@/components/workflow-v2/panels/TemplateInput.vue'

const props = defineProps<{
  selectedNode: any
  selectedEdge: any
  edges: any[]
  runStatus: any
}>()

const emit = defineEmits<{
  'update-node': [nodeId: string, data: any]
  'delete-node': [nodeId: string]
}>()

const activeTab = ref('properties')
const workflowStore = useWorkflowStore()

onMounted(() => {
  workflowStore.fetchCardTypes()
})

// 获取当前选中节点的定义
const nodeDefinition = computed(() => {
  if (!props.selectedNode) return null
  return workflowStore.getNodeType(props.selectedNode.type)
})

// 解析 JSON Schema 生成属性列表
const schemaProperties = computed(() => {
  const def = nodeDefinition.value
  if (!def || !def.config_schema || !def.config_schema.properties) return []
  
  const schema = def.config_schema
  const requiredSet = new Set(schema.required || [])
  
  return Object.entries(schema.properties).map(([name, conf]: [string, any]) => ({
    name,
    title: conf.title || conf.description || name,
    description: conf.description,
    type: conf.type,
    // JSON Schema 的 enum
    enum: conf.enum,
    // JSON Schema 的 default
    default: conf.default,
    required: requiredSet.has(name),
    rawSchema: conf
  }))
})

// 检测哪些输入端口被连线连接了
const connectedInputs = computed(() => {
  if (!props.selectedNode || !props.edges) {
    console.log('[连线检测] 无节点或边', { node: props.selectedNode?.id, hasEdges: !!props.edges })
    return new Set()
  }
  
  const nodeId = props.selectedNode.id
  const connected = new Set<string>()
  
  console.log('[连线检测] 开始检测', { nodeId, edgesCount: props.edges.length })
  
  // 遍历所有边，找到目标是当前节点的边
  props.edges.forEach((edge: any) => {
    if (edge.target === nodeId) {
      console.log('[连线检测] 找到目标边', { edge, targetHandle: edge.targetHandle })
      if (edge.targetHandle) {
        connected.add(edge.targetHandle)
      }
    }
  })
  
  console.log('[连线检测] 结果', { nodeId, connected: Array.from(connected) })
  return connected
})

// 检查某个配置项是否被连线连接
const isInputConnected = (inputName: string): boolean => {
  return connectedInputs.value.has(inputName)
}

// 日志类型定义
interface LogEntry {
  time: string
  level: 'debug' | 'info' | 'warn' | 'error'
  message: string
}

// 节点日志
const nodeLogs = computed<LogEntry[]>(() => {
  // 从runStatus中获取当前节点的日志
  if (!props.selectedNode || !props.runStatus) {
    return []
  }
  
  const nodeId = props.selectedNode.id
  const nodeState = props.runStatus.nodeStates?.[nodeId]
  
  return nodeState?.logs || []
})

// 节点输出显示（用于 Display 节点）
const nodeOutputDisplay = computed(() => {
  if (!props.selectedNode || !props.runStatus) {
    console.log('[输出显示] 无选中节点或运行状态')
    return null
  }
  
  const nodeId = props.selectedNode.id
  console.log('[输出显示] 当前节点:', nodeId)
  
  // runStatus.nodes 是一个数组，包含所有节点的状态
  const nodes = props.runStatus.nodes
  if (!nodes || !Array.isArray(nodes)) {
    console.log('[输出显示] nodes 不是数组:', nodes)
    return null
  }
  
  console.log('[输出显示] 节点列表:', nodes.map((n: any) => n.node_id))
  
  // 查找当前节点的状态
  const nodeState = nodes.find((n: any) => n.node_id === nodeId)
  if (!nodeState) {
    console.log('[输出显示] 未找到节点状态')
    return null
  }
  
  console.log('[输出显示] 节点状态:', nodeState)
  
  // 从 outputs_json 中获取 display 字段
  // outputs_json 可能是字符串（需要解析）或对象
  let outputs = nodeState.outputs_json
  console.log('[输出显示] outputs_json 类型:', typeof outputs, outputs)
  
  if (typeof outputs === 'string') {
    try {
      outputs = JSON.parse(outputs)
      console.log('[输出显示] 解析后的 outputs:', outputs)
    } catch (e) {
      console.error('解析 outputs_json 失败:', e)
      return null
    }
  }
  
  if (outputs && outputs.display) {
    console.log('[输出显示] 找到 display 数据:', outputs.display)
    return outputs.display
  }
  
  // Fallback: 如果没有 display 字段，但有输出数据，则显示原始 JSON
  if (outputs && Object.keys(outputs).length > 0) {
    return {
      type: 'json',
      title: '输出数据 (Raw)',
      content: JSON.stringify(outputs, null, 2)
    }
  }
  
  console.log('[输出显示] 无显示数据')
  return null
})

// 获取配置值
const getConfigValue = (name: string, defaultValue?: any) => {
  const val = props.selectedNode.data?.config?.[name]
  return val !== undefined ? val : defaultValue
}

// 更新配置
const updateConfig = (name: string, value: any) => {
  if (!props.selectedNode) return
  
  const newData = {
    ...props.selectedNode.data,
    config: {
      ...props.selectedNode.data.config,
      [name]: value
    }
  }
  
  emit('update-node', props.selectedNode.id, newData)
}

// 更新标签
const updateLabel = (value: string) => {
  if (!props.selectedNode) return
  
  const newData = {
    ...props.selectedNode.data,
    label: value
  }
  
  emit('update-node', props.selectedNode.id, newData)
}

// 更新描述
const updateDescription = (value: string) => {
  if (!props.selectedNode) return
  
  const newData = {
    ...props.selectedNode.data,
    description: value
  }
  
  emit('update-node', props.selectedNode.id, newData)
}

// 检测是否为对象或数组
const isObjectOrArray = (value: any): boolean => {
  return value !== null && typeof value === 'object'
}

// 格式化值为JSON字符串
const formatValue = (value: any): string => {
  if (value === null || value === undefined) return ''
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value, null, 2)
    } catch (e) {
      return String(value)
    }
  }
  return String(value)
}

// 从JSON字符串更新配置
const updateConfigFromJSON = (name: string, jsonString: string) => {
  try {
    const value = JSON.parse(jsonString)
    updateConfig(name, value)
  } catch (e) {
    // JSON解析失败，暂时不更新（用户可能还在编辑）
    console.warn('JSON解析失败:', e)
  }
}

// 获取智能 placeholder
const getPlaceholder = (prop: any): string => {
  // 如果被连线连接，显示连接提示
  if (isInputConnected(prop.name)) {
    return '留空则使用连线值，填写则覆盖'
  }
  
  // 特殊字段的智能提示
  if (prop.name === 'content_template') {
    return '留空则全量复制源数据 (推荐)'
  }
  if (prop.name === 'parent_id') {
    return '父卡片ID (可选)'  
  }
  
  // 默认使用 description
  return prop.description || ''
}

// 获取可用变量
const getVariables = (propName: string) => {
  const type = props.selectedNode?.type
  const vars: Array<{ label: string; value: string }> = []

  // 通用变量
  if (connectedInputs.value.has('input')) {
    vars.push({ label: '输入数据 {input}', value: '{input}' })
    vars.push({ label: '输入内容 {input.content}', value: '{input.content}' })
  }
  
  // 特定节点变量
  if (type === 'Card.BatchUpsert' || type === 'List.ForEach' || type === 'List.ForEachRange') {
    vars.push({ label: '当前项 {item}', value: '{item}' })
    vars.push({ label: '当前索引 {index}', value: '{index}' })
    
    // 针对 BatchUpsert 的常见字段提示
    if (propName === 'title_template') {
       vars.push({ label: '名称 {item.name}', value: '{item.name}' })
       vars.push({ label: '标题 {item.title}', value: '{item.title}' })
    }
    if (propName === 'content_template') {
       vars.push({ label: '分卷号 {item.volume_number}', value: '{item.volume_number}' })
       vars.push({ label: '完整项 {item}', value: '{item}' })
    }
  }

  // Card 相关
  if (type?.startsWith('Card.') && type !== 'Card.BatchUpsert') {
    vars.push({ label: '当前卡片 {card}', value: '{card}' })
    vars.push({ label: '卡片内容 {card.content}', value: '{card.content}' })
  }

  return vars
}

// 删除节点
const handleDelete = () => {
  if (!props.selectedNode) return
  emit('delete-node', props.selectedNode.id)
}
</script>

<style scoped lang="scss">
.property-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--el-bg-color);
  backdrop-filter: blur(10px);
  border-left: 1px solid var(--el-border-color-light);
}

html.dark .property-panel {
  background: rgba(45, 45, 45, 0.9);
}

.panel-header {
  padding: 20px;
  border-bottom: 1px solid var(--el-border-color-light);
  background: var(--el-bg-color);

  h3 {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
    color: var(--el-text-color-primary);
    display: flex;
    align-items: center;
    gap: 8px;
    
    &::before {
      content: '';
      display: block;
      width: 4px;
      height: 16px;
      background: var(--el-color-primary);
      border-radius: 2px;
    }
  }
}

.panel-content {
  flex: 1;
  overflow: hidden;

  :deep(.el-tabs) {
    height: 100%;
    display: flex;
    flex-direction: column;
    padding: 0 16px;
  }

  :deep(.el-tabs__header) {
    margin: 0 0 16px 0;
  }

  :deep(.el-tabs__content) {
    flex: 1;
    overflow: hidden;
  }

  :deep(.el-tab-pane) {
    height: 100%;
  }
}

.properties-section {
  padding: 24px;
  padding-bottom: 40px;
}

.property-item {
  margin-bottom: 24px;
  
  label {
    display: block;
    margin-bottom: 10px;
    font-size: 13px;
    color: var(--el-text-color-regular);
    font-weight: 500;
  }
}

.config-item {
  margin-bottom: 20px;
  background: var(--el-bg-color);
  padding: 12px;
  border-radius: var(--border-radius-sm);
  border: 1px solid var(--el-border-color);
  transition: all 0.2s;

  &:hover {
    border-color: var(--el-color-primary);
    box-shadow: var(--shadow-sm);
  }
  
  .config-label {
    display: flex;
    align-items: center;
    margin-bottom: 8px;
    font-size: 13px;
    color: var(--el-text-color-primary);
    font-weight: 600;
    
    .required-tag {
      margin-left: 8px;
      transform: scale(0.9);
    }
    
    .info-icon {
      margin-left: auto;
      color: var(--el-text-color-secondary);
      cursor: help;
    }
  }
}

.property-actions {
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.result-section {
  padding: 20px;
}

.result-block {
  margin-bottom: 24px;
  
  h4 {
    margin: 0 0 12px 0;
    font-size: 13px;
    font-weight: 600;
    color: var(--text-primary);
    display: flex;
    align-items: center;
    gap: 6px;
    
    .el-icon {
      color: var(--primary-color);
    }
  }
}

.empty-state {
  text-align: center;
  color: var(--el-text-color-secondary);
  padding: 24px 0;
  font-size: 13px;
  background: var(--el-fill-color-lighter);
  border-radius: var(--border-radius-sm);
}

.output-json,
.output-text {
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color);
  border-radius: var(--border-radius-sm);
  padding: 12px;
  max-height: 400px;
  overflow: auto;

  pre {
    margin: 0;
    font-family: 'Consolas', 'Monaco', monospace;
    font-size: 12px;
    line-height: 1.6;
    color: var(--el-text-color-primary);
    white-space: pre-wrap;
    word-wrap: break-word;
  }
}

.log-list {
  .log-item {
    padding: 10px;
    margin-bottom: 8px;
    background: var(--el-bg-color);
    border: 1px solid var(--el-border-color);
    border-radius: var(--border-radius-sm);
    font-size: 12px;
    display: flex;
    gap: 10px;
    align-items: flex-start;

    .log-time {
      color: var(--el-text-color-secondary);
      flex-shrink: 0;
      font-family: monospace;
    }

    .log-level {
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 11px;
      font-weight: 600;
      flex-shrink: 0;
      text-transform: uppercase;

      &.level-info {
        background: #e0f2fe;
        color: #0284c7;
      }

      &.level-error {
        background: #fee2e2;
        color: #dc2626;
      }

      &.level-warn {
        background: #fef3c7;
        color: #d97706;
      }
    }

    .log-message {
      flex: 1;
      color: var(--text-primary);
      line-height: 1.4;
    }
  }
}

.debug-content {
  padding: 10px;
  background: var(--el-fill-color-light);
  border-radius: var(--border-radius-sm);

  h5 {
    margin: 12px 0 6px 0;
    font-size: 12px;
    color: var(--el-text-color-secondary);
    
    &:first-child {
      margin-top: 0;
    }
  }

  .debug-data {
    background: var(--el-bg-color);
    padding: 10px;
    border: 1px solid var(--el-border-color);
    border-radius: 4px;
    font-size: 11px;
    line-height: 1.5;
    overflow-x: auto;
    margin-bottom: 0;
    color: var(--el-text-color-primary);
    font-family: 'Consolas', monospace;
  }
}

.panel-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.trigger-outputs {
  background: var(--el-fill-color-light);
  padding: 12px;
  border-radius: var(--border-radius-sm);
  border: 1px solid var(--el-border-color);

  .trigger-output-desc {
    font-size: 12px;
    color: var(--text-secondary);
    margin-bottom: 12px;
    line-height: 1.5;

    code {
      background: var(--el-fill-color-light);
      padding: 0 4px;
      border-radius: 3px;
      font-family: monospace;
      color: var(--el-color-primary);
    }
  }

  .output-var-item {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
    
    &:last-child {
      margin-bottom: 0;
    }

    .output-var-desc {
      font-size: 12px;
      color: var(--text-secondary);
    }
  }
}

.input-wrapper {
  position: relative;
  
  .connection-hint {
    margin-top: 6px;
    padding: 4px 8px;
    background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%);
    color: #1976d2;
    border: 1px solid #90caf9;
    border-radius: 4px;
    font-size: 11px;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-weight: 500;
    
    .el-icon {
      font-size: 12px;
      color: #1976d2;
    }
  }
}
</style>
