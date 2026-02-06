<template>
  <div class="node-block-editor">
    <!-- 节点块列表 -->
    <div class="node-blocks">
      <div
        v-for="(node, index) in nodes"
        :key="index"
        class="node-block"
        :class="{ 
          'is-selected': selectedIndex === index,
          'is-disabled': node.disabled
        }"
        @click="selectNode(index)"
        @dblclick="editNodeCode(index)"
      >
        <!-- 节点头部 -->
        <div class="node-block-header">
          <div class="node-info">
            <el-tag :type="getNodeCategoryColor(node.category)" size="small">
              {{ node.category }}
            </el-tag>
            <!-- 异步标识 -->
            <el-tag v-if="node.isAsync" type="warning" size="small" effect="dark">
              ⚡ 异步
            </el-tag>
            <!-- 变量名编辑 -->
            <el-input
              v-if="editingVariable?.nodeIndex === index"
              v-model="editingVariable.value"
              size="small"
              style="width: 120px"
              @blur="saveVariableEdit"
              @keydown.enter.stop="saveVariableEdit"
              @keydown.esc="cancelVariableEdit"
              ref="variableInputRef"
            />
            <span
              v-else
              class="node-variable editable"
              @click.stop="startVariableEdit(index, node.variable)"
              :title="点击编辑变量名"
            >
              {{ node.variable }}
            </span>
            <span class="node-type">{{ node.nodeType }}</span>
          </div>
          <div class="node-actions">
            <el-tooltip :content="node.isAsync ? '切换为同步' : '切换为异步'" placement="top">
              <el-button
                size="small"
                text
                @click.stop="toggleAsync(index)"
                :type="node.isAsync ? 'warning' : 'info'"
              >
                <template #icon>
                  <span style="font-size: 16px">{{ node.isAsync ? '⚡' : '🔄' }}</span>
                </template>
              </el-button>
            </el-tooltip>
            <el-tooltip :content="node.disabled ? '启用节点' : '禁用节点'" placement="top">
              <el-switch
                v-model="node.disabled"
                @change="toggleNodeDisabled(index)"
                size="small"
                inactive-text=""
                active-text=""
                :active-value="true"
                :inactive-value="false"
                style="--el-switch-on-color: #909399; --el-switch-off-color: #67c23a"
                @click.stop
              />
            </el-tooltip>
            <el-tooltip content="删除节点" placement="top">
              <el-button
                size="small"
                text
                type="danger"
                @click.stop="deleteNode(index)"
                :icon="Delete"
              />
            </el-tooltip>
          </div>
        </div>

        <!-- 节点参数编辑器 -->
        <div class="node-params" v-if="node.fields && node.fields.length > 0">
          <div class="params-header">
            <div class="params-title">参数</div>
            <el-button
              text
              size="small"
              @click.stop="toggleNodeCollapse(index)"
              :icon="node.collapsed ? ArrowRight : ArrowDown"
            />
          </div>
          <div v-if="!node.collapsed" v-for="(field, fieldIndex) in node.fields" :key="field.name" class="param-item">
            <span class="param-key">{{ field.label }}:</span>
            <div class="param-value-wrapper">
              <!-- 编辑模式 -->
              <div
                v-if="editingParam?.nodeIndex === index && editingParam?.fieldIndex === fieldIndex"
                class="smart-selector"
                style="flex: 1; display:flex; gap: 4px;"
              >
                <!-- ProjectSelect (x-component: ProjectSelect) -->
                <el-select
                  v-if="field.rawSchema?.['x-component'] === 'ProjectSelect'"
                  v-model="editingParam.value"
                  filterable
                  placeholder="选择项目"
                  size="small"
                  @change="saveParamEdit"
                >
                  <el-option
                    v-for="p in projectList"
                    :key="p.id"
                    :label="p.name"
                    :value="p.id"
                  />
                </el-select>

                <!-- LLMSelect (x-component: LLMSelect) -->
                <el-select
                  v-else-if="field.rawSchema?.['x-component'] === 'LLMSelect'"
                  v-model="editingParam.value"
                  filterable
                  placeholder="选择LLM配置"
                  size="small"
                  @change="saveParamEdit"
                >
                  <el-option
                    v-for="cfg in llmConfigList"
                    :key="cfg.id"
                    :label="cfg.display_name || cfg.model_name"
                    :value="cfg.id"
                  />
                </el-select>

                <!-- PromptSelect (x-component: PromptSelect) -->
                <el-select
                  v-else-if="field.rawSchema?.['x-component'] === 'PromptSelect'"
                  v-model="editingParam.value"
                  filterable
                  placeholder="选择提示词"
                  size="small"
                  @change="saveParamEdit"
                >
                  <el-option
                    v-for="prompt in promptList"
                    :key="prompt.id"
                    :label="prompt.name"
                    :value="prompt.id"
                  />
                </el-select>

                <!-- CardTypeSelect (x-component: CardTypeSelect) -->
                <el-select
                  v-else-if="field.rawSchema?.['x-component'] === 'CardTypeSelect'"
                  v-model="editingParam.value"
                  filterable
                  allow-create
                  default-first-option
                  placeholder="卡片类型"
                  size="small"
                  @change="saveParamEdit"
                >
                  <el-option
                    v-for="ct in cardTypeList"
                    :key="ct.id"
                    :label="ct.name"
                    :value="ct.name"
                  />
                </el-select>

                <!-- ResponseModelSelect (x-component: ResponseModelSelect) -->
                <el-select
                  v-else-if="field.rawSchema?.['x-component'] === 'ResponseModelSelect'"
                  v-model="editingParam.value"
                  filterable
                  placeholder="选择响应模型"
                  size="small"
                  @change="saveParamEdit"
                >
                  <el-option-group label="内置模型">
                    <el-option value="OneSentence" label="一句话梗概" />
                    <el-option value="ChapterOutline" label="章节大纲" />
                    <el-option value="VolumeOutline" label="分卷大纲" />
                    <el-option value="WorldBuilding" label="世界观设定" />
                    <el-option value="WritingGuide" label="写作指南" />
                    <el-option value="ParagraphOverview" label="段落概览" />
                  </el-option-group>
                  <el-option-group label="自定义卡片类型">
                    <el-option
                      v-for="ct in cardTypeList"
                      :key="ct.id"
                      :label="ct.name"
                      :value="ct.name"
                    />
                  </el-option-group>
                </el-select>

                <!-- Textarea (x-component: Textarea) -->
                <el-input
                  v-else-if="field.rawSchema?.['x-component'] === 'Textarea'"
                  v-model="editingParam.value"
                  type="textarea"
                  :rows="4"
                  size="small"
                  placeholder="输入内容"
                  @blur="saveParamEdit"
                />

                <!-- ToolMultiSelect (x-component: ToolMultiSelect) -->
                <el-select
                  v-else-if="field.rawSchema?.['x-component'] === 'ToolMultiSelect'"
                  v-model="editingParam.value"
                  filterable
                  multiple
                  collapse-tags
                  placeholder="选择工具"
                  size="small"
                  @change="saveParamEdit"
                >
                  <el-option value="search_cards" label="搜索卡片" />
                  <el-option value="create_card" label="创建卡片" />
                  <el-option value="update_card" label="更新卡片" />
                  <el-option value="delete_card" label="删除卡片" />
                  <el-option value="get_card" label="获取卡片" />
                  <el-option value="list_cards" label="列出卡片" />
                </el-select>

                <!-- Case 5: Boolean Switch -->
                <el-switch
                  v-else-if="field.type === 'boolean'"
                  v-model="editingParam.value"
                  size="small"
                  @change="saveParamEdit"
                />
                
                <!-- Case 6: Array Input (dynamic list) -->
                <div v-else-if="field.type === 'array'" style="flex: 1; display: flex; flex-direction: column; gap: 4px;">
                  <div
                    v-for="(item, itemIndex) in editingParam.arrayItems"
                    :key="itemIndex"
                    style="display: flex; gap: 4px;"
                  >
                    <el-input
                      v-model="editingParam.arrayItems[itemIndex]"
                      size="small"
                      placeholder="输入值"
                      style="flex: 1;"
                    />
                    <el-button
                      size="small"
                      type="danger"
                      :icon="Delete"
                      @click.stop="removeArrayItem(itemIndex)"
                    />
                  </div>
                  <el-button
                    size="small"
                    type="primary"
                    :icon="Plus"
                    @click.stop="addArrayItem"
                  >
                    添加项
                  </el-button>
                  <el-button
                    size="small"
                    type="success"
                    @click.stop="saveParamEdit"
                  >
                    保存
                  </el-button>
                </div>
                
                <!-- Case 7: Default Text Input -->
                <el-input
                  v-else
                  v-model="editingParam.value"
                  size="small"
                  @blur="saveParamEdit"
                  @keydown.enter.stop="saveParamEdit"
                >
                  <!-- Folder selection trigger for DirectorySelect -->
                  <template #append v-if="field.rawSchema?.['x-component'] === 'DirectorySelect'">
                    <el-button :icon="Folder" @click.stop="openFolderDialog" />
                  </template>
                </el-input>
              </div>

              <!-- 显示模式 -->
              <span
                v-else
                class="param-value editable"
                @click.stop="startParamEdit(index, fieldIndex)"
              >
                {{ formatDisplayValue(field) }}
                <el-tag v-if="field.required" size="small" type="danger" style="margin-left: 4px">必填</el-tag>
                <!-- 智能选择器提示图标 -->
                <el-icon v-if="isSmartSelectorField(field)" class="selector-icon">
                  <ArrowDown />
                </el-icon>
                <el-icon v-else-if="field.rawSchema?.['x-component'] === 'DirectorySelect'" class="selector-icon">
                  <Folder />
                </el-icon>
                <el-icon v-else class="edit-icon">
                  <EditPen />
                </el-icon>
              </span>
            </div>
          </div>
        </div>

        <!-- 节点输出字段 -->
        <div class="node-outputs" v-if="node.outputs && node.outputs.length > 0">
          <div class="outputs-title">输出字段</div>
          <div class="output-items">
            <el-tag
              v-for="output in node.outputs"
              :key="output.name"
              size="small"
              type="success"
              class="output-tag"
            >
              {{ node.variable }}.{{ output.name }}
            </el-tag>
          </div>
        </div>

        <!-- 执行状态（如果有） -->
        <div v-if="node.status" class="node-status" :class="`status-${node.status}`">
          <el-icon v-if="node.status === 'running'"><Loading /></el-icon>
          <el-icon v-else-if="node.status === 'completed'"><CircleCheck /></el-icon>
          <el-icon v-else-if="node.status === 'error'"><CircleClose /></el-icon>
          <span>{{ getStatusText(node.status) }}</span>
          <span v-if="node.progress !== undefined && node.status === 'running'">
            {{ node.progress }}%
          </span>
        </div>
      </div>

      <!-- 添加节点按钮 -->
      <div class="add-node-block" @click="showAddNodeDialog">
        <el-icon><Plus /></el-icon>
        <span>添加节点</span>
      </div>
    </div>

    <!-- 添加节点对话框 -->
    <el-dialog
      v-model="addNodeDialogVisible"
      title="添加节点"
      width="600px"
    >
      <el-select
        v-model="selectedNodeType"
        placeholder="选择节点类型"
        filterable
        style="width: 100%; margin-bottom: 16px"
      >
        <el-option-group
          v-for="(nodeList, category) in nodeTypesByCategory"
          :key="category"
          :label="category"
        >
          <el-option
            v-for="nodeType in nodeList"
            :key="nodeType.type"
            :label="`${nodeType.label} (${nodeType.type})`"
            :value="nodeType.type"
          >
            <div style="display: flex; flex-direction: column">
              <span>{{ nodeType.label }}</span>
              <span style="font-size: 12px; color: #909399">{{ nodeType.description }}</span>
            </div>
          </el-option>
        </el-option-group>
      </el-select>

      <el-input
        v-model="newNodeVariable"
        placeholder="变量名，例如: project"
        style="width: 100%"
      />

      <template #footer>
        <el-button @click="addNodeDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="addNode">添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Edit, Delete, Loading, CircleCheck, CircleClose, EditPen, Folder, ArrowDown, ArrowRight } from '@element-plus/icons-vue'
import request from '@/api/request'
import { storeToRefs } from 'pinia'
import { useProjectListStore } from '@/stores/useProjectListStore'
import { useLLMConfigStore } from '@/stores/useLLMConfigStore'
import { usePromptStore } from '@/stores/usePromptStore'
import { useCardStore } from '@/stores/useCardStore'
import { ParameterFormatter } from '@/utils/parameterFormatter'

const props = defineProps({
  modelValue: {
    type: String,
    default: ''
  },
  isRunning: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:modelValue', 'node-selected'])

// 使用 stores
const projectListStore = useProjectListStore()
const llmConfigStore = useLLMConfigStore()
const promptStore = usePromptStore()
const cardStore = useCardStore()

// 从 stores 获取响应式数据
const { projects: projectList } = storeToRefs(projectListStore)
const { llmConfigs: llmConfigList } = storeToRefs(llmConfigStore)
const { prompts: promptList } = storeToRefs(promptStore)
const { cardTypes: cardTypeList } = storeToRefs(cardStore)

// 状态
const nodes = ref([])
const selectedIndex = ref(-1)
const addNodeDialogVisible = ref(false)
const selectedNodeType = ref('')
const newNodeVariable = ref('')
const nodeTypes = ref([])
// 参数编辑状态
const editingParam = ref(null)
const paramInputRef = ref(null)
// 变量名编辑状态
const editingVariable = ref(null)
const variableInputRef = ref(null)
// 智能选择器数据
const variableList = ref([]) // 所有的变量列表
const fileDialogVisible = ref(false)
// 内部更新标记
const isInternalUpdate = ref(false)

// 按分类组织的节点类型
const nodeTypesByCategory = computed(() => {
  const grouped = {}
  nodeTypes.value.forEach(nodeType => {
    if (!grouped[nodeType.category]) {
      grouped[nodeType.category] = []
    }
    grouped[nodeType.category].push(nodeType)
  })
  return grouped
})

// 解析代码为节点块
async function parseCodeToNodes(code) {
  if (!code || !code.trim()) return []

  try {
    // 直接发送代码给后端解析（后端会处理元数据注释）
    const response = await request.post('/workflows/parse', { code }, '/api')
    
    if (!response.success || !response.statements) {
      const errorMsg = response.errors?.join('; ') || '未知错误'
      console.error('代码解析失败:', response.errors)
      throw new Error(errorMsg)
    }
    
    console.log(`[parseCodeToNodes] 解析了 ${response.statements.length} 个语句`)
    
    const parsedNodes = []
    
    // 构建节点
    for (let i = 0; i < response.statements.length; i++) {
      const stmt = response.statements[i]
      
      console.log(`[parseCodeToNodes] 语句 ${i}: ${stmt.variable} (行${stmt.line}), disabled=${stmt.disabled}, async=${stmt.is_async}`)
        
      // 处理节点调用
      if (stmt.node_type && stmt.node_type !== 'expression' && stmt.node_type !== '_wait') {
        const parts = stmt.node_type.split('.')
        const category = parts[0]
        const method = parts.slice(1).join('.')
        
        const node = {
          variable: stmt.variable,
          category: category,
          method: method,
          nodeType: stmt.node_type,
          params: stmt.config || {},
          code: stmt.code,
          outputs: [],
          collapsed: false,
          disabled: stmt.disabled || false,  // 从后端获取
          isAsync: stmt.is_async || false    // 从后端获取
        }
        
        await fetchNodeOutputs(node)
        parsedNodes.push(node)
      } else {
        // 处理纯表达式、wait语句或其他非标准节点
        parsedNodes.push({
          variable: stmt.variable,
          category: 'Raw',
          method: 'Code',
          nodeType: stmt.node_type || 'Raw.Code',
          params: stmt.config || {},
          code: stmt.code,
          outputs: [],
          collapsed: false,
          disabled: stmt.disabled || false,
          isAsync: stmt.is_async || false
        })
      }
    }
    return parsedNodes
  } catch (error) {
    console.error('解析请求失败:', error)
    // 重新抛出异常，让调用者处理
    throw error
  }
}

// 获取节点的输入输出字段
async function fetchNodeOutputs(node) {
  try {
    const response = await request.get(`/nodes/${node.nodeType}/metadata`, undefined, '/api', {
      showLoading: false
    })
    node.outputs = response.outputs || []

    // 合并字段定义和参数值，构建统一的字段列表
    const schema = response.input_schema?.properties || {}
    const hiddenFields = ['debug', 'debug_mode', 'verbose', 'log_level']
    
    // 首先从 schema 创建字段
    const schemaFields = Object.entries(schema)
      .filter(([fieldName]) => !hiddenFields.includes(fieldName))
      .map(([fieldName, fieldDef]) => {
        // 从 params 中获取原始值
        let rawValue = node.params?.[fieldName]
        
        // 格式化为字符串（用于显示和代码生成）
        let formattedValue = ''
        
        if (rawValue !== undefined && rawValue !== null && rawValue !== '') {
          const fieldType = fieldDef.type
          
          console.log(`[fetchNodeOutputs] 处理字段 ${fieldName}:`, {
            fieldType,
            rawValue,
            rawValueType: typeof rawValue,
            isObject: typeof rawValue === 'object',
            isArray: Array.isArray(rawValue)
          })
          
          // 始终使用 ParameterFormatter 格式化
          try {
            formattedValue = ParameterFormatter.format({
              type: fieldType,
              value: rawValue
            })
            
            console.log(`[fetchNodeOutputs] 格式化成功 ${fieldName}:`, {
              formattedValue,
              formattedType: typeof formattedValue
            })
            
            // 确保返回的是字符串
            if (typeof formattedValue !== 'string') {
              console.warn(`[fetchNodeOutputs] 格式化结果不是字符串，强制转换: ${fieldName}`)
              formattedValue = JSON.stringify(formattedValue)
            }
          } catch (e) {
            console.error(`[fetchNodeOutputs] 格式化字段 ${fieldName} 失败:`, e, 'rawValue:', rawValue)
            // 降级处理：确保返回字符串
            if (typeof rawValue === 'object' && rawValue !== null) {
              formattedValue = JSON.stringify(rawValue)
            } else {
              formattedValue = String(rawValue)
            }
            console.log(`[fetchNodeOutputs] 降级处理后 ${fieldName}:`, formattedValue)
          }
        }
        
        return {
          name: fieldName,
          label: fieldDef.description || fieldName,
          type: fieldDef.type,
          required: fieldDef.required || false,
          default: fieldDef.default,
          value: formattedValue,  // 确保是字符串
          rawSchema: fieldDef  // 保存原始 schema，用于获取 x-component
        }
      })
    
    // 然后添加不在 schema 中但存在于 params 的字段
    const schemaFieldNames = new Set(Object.keys(schema))
    const extraFields = Object.entries(node.params || {})
      .filter(([fieldName]) => !schemaFieldNames.has(fieldName) && !hiddenFields.includes(fieldName))
      .map(([fieldName, rawValue]) => {
        // 推断类型
        let fieldType = 'string'
        if (typeof rawValue === 'number') {
          fieldType = Number.isInteger(rawValue) ? 'integer' : 'number'
        } else if (typeof rawValue === 'boolean') {
          fieldType = 'boolean'
        } else if (Array.isArray(rawValue)) {
          fieldType = 'array'
        } else if (typeof rawValue === 'object' && rawValue !== null) {
          fieldType = 'object'
        }
        
        console.log(`[fetchNodeOutputs] 处理额外字段 ${fieldName}:`, {
          fieldType,
          rawValue,
          rawValueType: typeof rawValue
        })
        
        // 格式化值（确保返回字符串）
        let formattedValue = ''
        try {
          formattedValue = ParameterFormatter.format({
            type: fieldType,
            value: rawValue
          })
          
          console.log(`[fetchNodeOutputs] 额外字段格式化成功 ${fieldName}:`, {
            formattedValue,
            formattedType: typeof formattedValue
          })
          
          // 确保返回的是字符串
          if (typeof formattedValue !== 'string') {
            console.warn(`[fetchNodeOutputs] 额外字段格式化结果不是字符串，强制转换: ${fieldName}`)
            formattedValue = JSON.stringify(formattedValue)
          }
        } catch (e) {
          console.error(`[fetchNodeOutputs] 格式化额外字段 ${fieldName} 失败:`, e, 'rawValue:', rawValue)
          // 降级处理：确保返回字符串
          if (typeof rawValue === 'object' && rawValue !== null) {
            formattedValue = JSON.stringify(rawValue)
          } else {
            formattedValue = String(rawValue)
          }
          console.log(`[fetchNodeOutputs] 额外字段降级处理后 ${fieldName}:`, formattedValue)
        }
        
        return {
          name: fieldName,
          label: fieldName,
          type: fieldType,
          required: false,
          default: undefined,
          value: formattedValue,  // 确保是字符串
          rawSchema: null  // 额外字段没有 schema
        }
      })
    
    // 合并字段列表
    node.fields = [...schemaFields, ...extraFields]

    console.log('[fetchNodeOutputs] 节点字段:', node.nodeType, node.fields)
  } catch (error) {
    console.error('获取节点元数据失败:', error)
    node.outputs = []
    node.fields = []
  }
}

// 解析参数字符串
function parseParams(paramsStr) {
  const params = {}
  if (!paramsStr.trim()) return params

  // 简单的参数解析
  const paramRegex = /(\w+)\s*=\s*([^,]+)/g
  let match

  while ((match = paramRegex.exec(paramsStr)) !== null) {
    const [, key, value] = match
    params[key] = value.trim().replace(/^["']|["']$/g, '')
  }

  return params
}

// 将节点块转换为XML格式代码
function nodesToCode() {
  const xmlNodes = nodes.value.map((node, idx) => {
    if (!node.variable || !node.nodeType) {
      console.warn(`[nodesToCode] 节点 ${idx} 缺少必要信息`)
      return ''
    }
    
    // 构建参数列表
    const paramParts = (node.fields || [])
      .filter(f => f.value !== undefined && f.value !== null && f.value !== '')
      .map(f => {
        console.log(`[nodesToCode] 节点 ${idx} 字段 ${f.name}:`, {
          type: f.type,
          value: f.value,
          valueType: typeof f.value
        })
        
        // field.value 应该已经在 fetchNodeOutputs 中格式化为字符串
        let paramValue = f.value
        
        // 安全检查：如果仍然是对象，强制转换
        if (typeof paramValue === 'object' && paramValue !== null) {
          console.error(`[nodesToCode] 字段 ${f.name} 的值仍然是对象！强制转换:`, paramValue)
          try {
            paramValue = ParameterFormatter.format({
              type: f.type || 'object',
              value: paramValue
            })
          } catch (e) {
            console.error(`[nodesToCode] 格式化失败，使用 JSON.stringify:`, e)
            paramValue = JSON.stringify(paramValue)
          }
        }
        
        // 最终检查：确保不是 [object Object]
        const paramStr = String(paramValue)
        if (paramStr === '[object Object]') {
          console.error(`[nodesToCode] 检测到 [object Object]！字段: ${f.name}, 原始值:`, f.value)
          // 尝试修复
          try {
            paramValue = JSON.stringify(f.value)
          } catch (e) {
            paramValue = '""'  // 降级为空字符串
          }
        }
        
        return `${f.name}=${paramValue}`
      })
    
    // 构建节点调用表达式（不包含变量赋值）
    const callExpr = `${node.nodeType}(${paramParts.join(', ')})`
    
    // 构建XML节点
    const attrs = [`name="${node.variable}"`]
    if (node.isAsync) attrs.push('async="true"')
    if (node.disabled) attrs.push('disabled="true"')
    
    const xmlNode = `<node ${attrs.join(' ')}>
  ${callExpr}
</node>`
    
    console.log(`[nodesToCode] 节点 ${idx} (${node.variable}):`, xmlNode)
    return xmlNode
  }).filter(code => code.trim() !== '')
  
  const result = xmlNodes.join('\n\n')
  console.log('[nodesToCode] 生成XML代码，节点数:', nodes.value.length)
  console.log('[nodesToCode] 最终代码:\n', result)
  return result
}

// 选择节点
function selectNode(index) {
  selectedIndex.value = index
  emit('node-selected', nodes.value[index])
}

// 删除节点
function deleteNode(index) {
  nodes.value.splice(index, 1)
  if (selectedIndex.value === index) {
    selectedIndex.value = -1
    emit('node-selected', null)
  } else if (selectedIndex.value > index) {
    selectedIndex.value--
  }
  
  // 触发代码更新
  emit('update:modelValue', nodesToCode())
}

// 切换节点禁用状态
async function toggleNodeDisabled(index) {
  const node = nodes.value[index]
  const targetDisabledState = node.disabled
  console.log(`[toggleNodeDisabled] 节点 ${node.variable} 禁用状态: ${targetDisabledState}`)
  
  // 标记为内部更新，避免 watch 重新解析
  isInternalUpdate.value = true
  
  // 重新生成XML代码（disabled属性会自动包含在XML中）
  emit('update:modelValue', nodesToCode())
  
  const message = targetDisabledState ? '节点已禁用' : '节点已启用'
  ElMessage.success(message)
}

// 切换异步/同步
async function toggleAsync(index) {
  const node = nodes.value[index]
  
  // 切换 isAsync 状态
  node.isAsync = !node.isAsync
  
  const targetAsyncState = node.isAsync
  
  // 标记为内部更新，避免 watch 重新解析
  isInternalUpdate.value = true
  
  // 重新生成XML代码（async属性会自动包含在XML中）
  const newCode = nodesToCode()
  
  // 发送代码更新事件
  emit('update:modelValue', newCode)
  
  // 重新解析代码，确保可视化视图与代码同步
  try {
    const parsedNodes = await parseCodeToNodes(newCode)
    
    // 使用 splice 逐个替换节点，触发 Vue 响应式更新
    parsedNodes.forEach((parsedNode, idx) => {
      if (idx < nodes.value.length) {
        nodes.value.splice(idx, 1, parsedNode)
      } else {
        nodes.value.push(parsedNode)
      }
    })
    
    if (parsedNodes.length < nodes.value.length) {
      nodes.value.splice(parsedNodes.length)
    }
  } catch (error) {
    console.error('[toggleAsync] 重新解析失败:', error)
  }
  
  const message = targetAsyncState ? '已切换为异步节点' : '已切换为同步节点'
  ElMessage.success(message)
}

// 显示添加节点对话框
function showAddNodeDialog() {
  selectedNodeType.value = ''
  newNodeVariable.value = ''
  addNodeDialogVisible.value = true
}

// 添加节点
async function addNode() {
  if (!selectedNodeType.value || !newNodeVariable.value) {
    ElMessage.warning('请选择节点类型并输入变量名')
    return
  }

  try {
    // 生成XML格式的节点代码
    const code = `<node name="${newNodeVariable.value}">
  ${selectedNodeType.value}()
</node>`
    
    console.log('[addNode] 生成的XML代码:\n', code)
    
    const parsed = await parseCodeToNodes(code)

    if (parsed && parsed.length > 0) {
      console.log('[addNode] 解析后的节点:', parsed[0])
      
      // 标记为内部更新，避免触发 watch 重新解析
      isInternalUpdate.value = true
      
      nodes.value.push(parsed[0])
      
      const finalCode = nodesToCode()
      console.log('[addNode] 最终生成的代码:\n', finalCode)
      
      emit('update:modelValue', finalCode)
      selectedIndex.value = nodes.value.length - 1
      emit('node-selected', nodes.value[selectedIndex.value])
      ElMessage.success('节点已添加')
    } else {
      ElMessage.error('节点添加失败：代码解析失败')
    }
  } catch (error) {
    console.error('[addNode] 添加节点失败:', error)
    ElMessage.error(`节点添加失败：${error.message || error}`)
  }

  addNodeDialogVisible.value = false
}

// 开始编辑参数
function startParamEdit(nodeIndex, fieldIndex) {
  const node = nodes.value[nodeIndex]
  const field = node.fields[fieldIndex]
  
  console.log('[startParamEdit] 开始编辑:', { nodeIndex, fieldIndex, field })
  
  // 获取当前值，去掉引号和 $ 前缀
  let editValue = field.value
  if (editValue === undefined || editValue === null) {
    editValue = field.default || (field.type === 'boolean' ? false : '')
  }
  
  console.log('[startParamEdit] 原始值:', { 
    fieldName: field.name, 
    fieldType: field.type, 
    editValue, 
    isArray: Array.isArray(editValue),
    valueType: typeof editValue
  })
  
  // 处理布尔值
  if (field.type === 'boolean') {
    // 将字符串 "True"/"False" 转换为布尔值
    if (typeof editValue === 'string') {
      editValue = editValue === 'True' || editValue === 'true'
    }
  }
  // 处理数组类型
  else if (field.type === 'array') {
    // 先去掉外层的引号（如果有）
    if (typeof editValue === 'string') {
      if ((editValue.startsWith('"') && editValue.endsWith('"')) || 
          (editValue.startsWith("'") && editValue.endsWith("'"))) {
        editValue = editValue.substring(1, editValue.length - 1)
        console.log('[startParamEdit] 去掉外层引号后:', editValue)
      }
    }
    
    // 将数组转换为可编辑的数组项
    let arrayItems = []
    if (Array.isArray(editValue)) {
      arrayItems = editValue.map(item => {
        // 去掉字符串的引号
        const str = String(item)
        if ((str.startsWith('"') && str.endsWith('"')) || (str.startsWith("'") && str.endsWith("'"))) {
          return str.substring(1, str.length - 1)
        }
        return str
      })
    }
    // 如果是字符串形式的数组 ["A1", "A2"]，解析它
    else if (typeof editValue === 'string' && editValue.startsWith('[') && editValue.endsWith(']')) {
      try {
        // 先尝试 JSON 解析
        const parsed = JSON.parse(editValue.replace(/'/g, '"'))
        arrayItems = parsed.map(item => {
          const str = String(item)
          // 去掉引号
          if ((str.startsWith('"') && str.endsWith('"')) || (str.startsWith("'") && str.endsWith("'"))) {
            return str.substring(1, str.length - 1)
          }
          return str
        })
      } catch (e) {
        // 解析失败，手动分割
        const content = editValue.substring(1, editValue.length - 1) // 去掉 [ ]
        arrayItems = content.split(',').map(s => {
          const trimmed = s.trim()
          // 去掉引号
          if ((trimmed.startsWith('"') && trimmed.endsWith('"')) || (trimmed.startsWith("'") && trimmed.endsWith("'"))) {
            return trimmed.substring(1, trimmed.length - 1)
          }
          return trimmed
        }).filter(item => item)
      }
    }
    // 如果是逗号分隔的字符串
    else if (typeof editValue === 'string' && editValue.includes(',')) {
      arrayItems = editValue.split(',').map(s => s.trim()).filter(item => item)
    }
    // 单个值
    else if (editValue) {
      arrayItems = [String(editValue)]
    }
    
    console.log('[startParamEdit] 数组解析结果:', arrayItems)
    
    // 保存到 editingParam
    editValue = arrayItems
  }
  // 如果是字符串类型且有引号，去掉引号
  else if (typeof editValue === 'string' && field.type === 'string') {
    if ((editValue.startsWith('"') && editValue.endsWith('"')) || 
        (editValue.startsWith("'") && editValue.endsWith("'"))) {
      editValue = editValue.substring(1, editValue.length - 1)
    }
  }
  
  editingParam.value = {
    nodeIndex,
    fieldIndex,
    fieldName: field.name,
    fieldType: field.type,
    value: field.type === 'array' ? null : editValue,  // 数组类型不使用 value
    arrayItems: field.type === 'array' ? editValue : []  // 数组类型使用 arrayItems
  }
  
  console.log('[startParamEdit] 编辑状态:', editingParam.value)
}

// 添加数组项
function addArrayItem() {
  if (!editingParam.value || !editingParam.value.arrayItems) return
  editingParam.value.arrayItems.push('')
}

// 删除数组项
function removeArrayItem(index) {
  if (!editingParam.value || !editingParam.value.arrayItems) return
  editingParam.value.arrayItems.splice(index, 1)
}

// 保存参数编辑
async function saveParamEdit() {
  if (!editingParam.value) return
  
  const { nodeIndex, fieldIndex, fieldName, fieldType, value, arrayItems } = editingParam.value
  const node = nodes.value[nodeIndex]
  
  if (!node || !node.fields || !node.fields[fieldIndex]) {
    console.error('[saveParamEdit] 节点或字段不存在:', { nodeIndex, fieldIndex })
    ElMessage.error('保存失败：节点数据异常')
    editingParam.value = null
    return
  }
  
  const field = node.fields[fieldIndex]
  
  console.log('[saveParamEdit] 保存参数:', { 
    nodeIndex, 
    fieldIndex, 
    fieldName, 
    fieldType, 
    value,
    node: {
      variable: node.variable,
      nodeType: node.nodeType,
      fieldsCount: node.fields.length
    }
  })
  
  try {
    // 处理数组类型
    let finalValue = value
    if (fieldType === 'array' && arrayItems) {
      // 过滤掉空项
      const filteredItems = arrayItems.filter(item => item && item.trim())
      finalValue = filteredItems
      console.log('[saveParamEdit] 数组项:', filteredItems)
    }
    
    // 使用 ParameterFormatter 处理空值
    if (ParameterFormatter.isEmpty(finalValue)) {
      console.log('[saveParamEdit] 值为空，清除字段值')
      field.value = undefined
      
      // 标记为内部更新，避免触发 watch 重新解析
      isInternalUpdate.value = true
      
      // 重新生成XML代码（不包含该字段）
      const allCode = nodesToCode()
      console.log('[saveParamEdit] 完整代码:\n', allCode)
      emit('update:modelValue', allCode)
      ElMessage.success('参数已清除')
      
      editingParam.value = null
      return
    }
    
    // 使用 ParameterFormatter 格式化值
    const formattedValue = ParameterFormatter.format({
      type: fieldType,
      value: finalValue
    })
    
    console.log('[saveParamEdit] 格式化后的值:', formattedValue)
    
    // 更新字段值
    field.value = formattedValue
    
    console.log('[saveParamEdit] 当前所有节点:')
    nodes.value.forEach((n, idx) => {
      console.log(`  [${idx}] ${n.variable}: fields=`, n.fields?.map(f => `${f.name}=${f.value}`))
    })
    
    // 标记为内部更新，避免触发 watch 重新解析
    isInternalUpdate.value = true
    
    // 重新生成XML代码
    const allCode = nodesToCode()
    console.log('[saveParamEdit] 完整XML代码:\n', allCode)
    
    // 验证生成的代码是否有效
    if (!allCode || allCode.trim() === '') {
      throw new Error('生成的代码为空')
    }
    
    emit('update:modelValue', allCode)
    ElMessage.success('参数已更新')
    
    editingParam.value = null
  } catch (error) {
    console.error('[saveParamEdit] 保存参数失败:', error)
    ElMessage.error(`保存失败：${error.message}`)
    editingParam.value = null
  }
}


// 打开文件夹选择对话框
async function openFolderDialog() {
  try {
    const result = await window.electron.ipcRenderer.invoke('dialog:openDirectory')
    if (result && !result.canceled && result.filePaths.length > 0) {
      if (editingParam.value) {
        const path = result.filePaths[0]
        // 转义 Windows 路径反斜杠
        editingParam.value.value = path.replace(/\\/g, '\\\\')
        // 自动保存
        saveParamEdit()
      }
    }
  } catch (e) {
    console.error('Failed to open directory dialog:', e)
  }
}

// 显示可用参数（当节点没有参数时）
function showAvailableParams(nodeIndex) {
  const node = nodes.value[nodeIndex]
  if (!node.fields || node.fields.length === 0) {
    ElMessage.info('该节点没有可配置的参数')
    return
  }
  
  // 为所有必填字段添加空值
  node.fields.forEach(field => {
    if (field.required && !field.value) {
      field.value = field.default || ''
    }
  })
  
  // 触发更新
  emit('update:modelValue', nodesToCode())
}

// 格式化参数值
function formatParamValue(value) {
  // 处理空值
  if (value === undefined || value === null || value === '') {
    return '(未设置)'
  }
  
  // 转换为字符串
  const strValue = String(value)
  
  // 截断过长的字符串
  if (strValue.length > 50) {
    return strValue.substring(0, 50) + '...'
  }
  
  return strValue
}

// 获取节点分类颜色
function getNodeCategoryColor(category) {
  const colors = {
    'Logic': 'primary',
    'Novel': 'success',
    'Card': 'warning',
    'AI': 'danger',
    'Prompt': 'info'
  }
  return colors[category] || 'info'
}

// 获取状态文本
function getStatusText(status) {
  const texts = {
    'running': '运行中',
    'completed': '已完成',
    'error': '失败'
  }
  return texts[status] || ''
}

// 加载节点类型
async function loadNodeTypes() {
  try {
    const response = await request.get('/nodes/types', undefined, '/api', { showLoading: false })
    nodeTypes.value = response.node_types || []
  } catch (error) {
    console.error('加载节点类型失败:', error)
  }
}

// 监听代码变化
watch(() => props.modelValue, async (newCode, oldCode) => {
  // 如果是内部更新（saveParamEdit/saveVariableEdit 触发），跳过重新解析
  if (isInternalUpdate.value) {
    console.log('[watch] 内部更新，跳过重新解析')
    isInternalUpdate.value = false
    return
  }
  
  console.log('[watch] 外部代码变化，重新解析')
  console.log('[watch] 新代码长度:', newCode?.length, '旧代码长度:', oldCode?.length)
  console.log('[watch] 新代码:\n', newCode)
  
  try {
    const parsedNodes = await parseCodeToNodes(newCode)
    console.log('[watch] 解析成功，节点数:', parsedNodes.length)
    nodes.value = parsedNodes
  } catch (error) {
    console.error('[watch] 代码解析失败:', error)
    console.error('[watch] 失败的代码:\n', newCode)
    // 解析失败时保持当前节点列表不变
    // 只有在非初始化时才显示错误提示（避免组件挂载时的错误提示）
    if (oldCode !== undefined) {
      ElMessage.error(`代码解析失败：${error.message || error}`)
    }
  }
}, { immediate: true })

// 更新变量列表（从现有节点中提取）
function updateVariableList() {
  const vars = []
  nodes.value.forEach(node => {
     if (node.variable) {
        vars.push({
           value: node.variable,
           label: node.variable,
           type: 'variable'
        })
        // 如果有输出字段，我也加进去? 还是只加根变量?
        // 暂只加根变量
     }
  })
  variableList.value = vars
}

// 判断字段是否需要智能选择器（基于 x-component）
function isSmartSelectorField(field) {
  if (!field || !field.rawSchema) return false
  const xComponent = field.rawSchema['x-component']
  return ['ProjectSelect', 'LLMSelect', 'PromptSelect', 'CardTypeSelect', 'ResponseModelSelect', 'ToolMultiSelect'].includes(xComponent)
}

// 切换节点折叠状态
function toggleNodeCollapse(index) {
  const node = nodes.value[index]
  node.collapsed = !node.collapsed
}

// 开始编辑变量名
function startVariableEdit(nodeIndex, currentVariable) {
  console.log('[startVariableEdit] 开始编辑变量名:', { nodeIndex, currentVariable })
  
  editingVariable.value = {
    nodeIndex,
    value: currentVariable,
    originalValue: currentVariable
  }
  
  nextTick(() => {
    if (variableInputRef.value) {
      variableInputRef.value.focus()
      variableInputRef.value.select()
    }
  })
}

// 保存变量名编辑
async function saveVariableEdit() {
  console.log('[saveVariableEdit] 函数被调用')
  console.log('[saveVariableEdit] editingVariable:', editingVariable.value)
  
  if (!editingVariable.value) {
    console.log('[saveVariableEdit] editingVariable 为空，退出')
    return
  }
  
  const { nodeIndex, value, originalValue } = editingVariable.value
  const newVariable = value.trim()
  
  console.log('[saveVariableEdit] 保存变量名:', { nodeIndex, newVariable, originalValue })
  
  // 验证变量名
  if (!newVariable) {
    ElMessage.error('变量名不能为空')
    editingVariable.value = null
    return
  }
  
  // 验证变量名格式
  if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(newVariable)) {
    ElMessage.error('变量名只能包含字母、数字、下划线，且不能以数字开头')
    editingVariable.value = null
    return
  }
  
  // 检查是否与其他节点重名
  const isDuplicate = nodes.value.some((n, idx) => idx !== nodeIndex && n.variable === newVariable)
  if (isDuplicate) {
    ElMessage.error(`变量名 "${newVariable}" 已被使用`)
    editingVariable.value = null
    return
  }
  
  // 如果没有变化，直接返回
  if (newVariable === originalValue) {
    editingVariable.value = null
    return
  }
  
  console.log('[saveVariableEdit] 开始更新变量名和引用...')
  
  const allCode = nodesToCode()
  console.log('[saveVariableEdit] 原始代码:\n', allCode)
  
  try {
    // 调用后端 API 进行变量重命名
    console.log('[saveVariableEdit] 准备调用后端 API...')
    console.log('[saveVariableEdit] 请求参数:', {
      code: allCode,
      old_name: originalValue,
      new_name: newVariable
    })
    
    const response = await request.post('/workflows/rename-variable', {
      code: allCode,
      old_name: originalValue,
      new_name: newVariable
    }, '/api')
    
    console.log('[saveVariableEdit] 收到响应:', response)
    
    if (response.success && response.new_code) {
      console.log('[saveVariableEdit] 新代码:\n', response.new_code)
      
      // 发送更新事件
      emit('update:modelValue', response.new_code)
      
      // 强制重新解析代码以更新显示
      try {
        nodes.value = await parseCodeToNodes(response.new_code)
        console.log('[saveVariableEdit] 节点已重新解析')
      } catch (error) {
        console.error('[saveVariableEdit] 重新解析失败:', error)
      }
      
      ElMessage.success(`变量名已更新：${originalValue} → ${newVariable}`)
    } else {
      console.error('[saveVariableEdit] 重命名失败:', response.error)
      ElMessage.error(`重命名失败：${response.error || '未知错误'}`)
    }
  } catch (error) {
    console.error('[saveVariableEdit] 重命名请求失败:', error)
    ElMessage.error(`重命名失败：${error.message || error}`)
  }
  
  editingVariable.value = null
}

// 取消变量名编辑
function cancelVariableEdit() {
  editingVariable.value = null
}

// 格式化显示值（去掉引号和 $ 前缀）
function formatDisplayValue(field) {
  if (ParameterFormatter.isEmpty(field.value)) {
    return field.default || '(未设置)'
  }
  
  // 使用 ParameterFormatter 解析显示值
  let displayValue = ParameterFormatter.parseDisplayValue(field.value)
  
  // 对于智能选择器，显示对应的名称而不是 ID
  const xComponent = field.rawSchema?.['x-component']
  
  if (xComponent === 'ProjectSelect') {
    // 显示项目名称
    const projectId = parseInt(displayValue)
    const project = projectList.value.find(p => p.id === projectId)
    if (project) {
      displayValue = project.name
    }
  } else if (xComponent === 'LLMSelect') {
    // 显示 LLM 配置名称
    const llmConfigId = parseInt(displayValue)
    const llmConfig = llmConfigList.value.find(cfg => cfg.id === llmConfigId)
    if (llmConfig) {
      displayValue = llmConfig.display_name || llmConfig.model_name || `LLM #${llmConfigId}`
    }
  } else if (xComponent === 'PromptSelect') {
    // 显示提示词名称
    const promptId = parseInt(displayValue)
    const prompt = promptList.value.find(p => p.id === promptId)
    if (prompt) {
      displayValue = prompt.name
    }
  }
  
  // 截断过长的值
  return displayValue.length > 50 ? displayValue.substring(0, 50) + '...' : displayValue
}

// 组件挂载时加载节点类型和数据
onMounted(async () => {
  loadNodeTypes()

  // 使用 stores 加载数据
  try {
    await Promise.all([
      projectListStore.fetchProjects(),
      llmConfigStore.fetchLLMConfigs(),
      promptStore.fetchPrompts(),
      cardStore.fetchInitialData() // 这会加载 cardTypes
    ])

    // 调试日志
    console.log('[NodeBlockEditor] 数据加载完成:')
    console.log('  - 项目列表:', projectList.value.length, '个')
    console.log('  - LLM配置:', llmConfigList.value.length, '个')
    console.log('  - 提示词:', promptList.value.length, '个')
    console.log('  - 卡片类型:', cardTypeList.value.length, '个')
  } catch (error) {
    console.error('加载数据失败:', error)
  }
})
</script>

<style scoped>
.node-block-editor {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--el-bg-color-page);
}

.node-blocks {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.node-block {
  margin-bottom: 12px;
  padding: 16px;
  background: var(--el-bg-color);
  border: 2px solid var(--el-border-color);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s;
}

.node-block:hover {
  border-color: var(--el-color-primary);
  box-shadow: 0 2px 12px var(--el-box-shadow-light);
}

.node-block.is-selected {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.node-block.is-disabled {
  opacity: 0.5;
  background: var(--el-fill-color-light);
  border-color: var(--el-border-color-light);
  position: relative;
}

.node-block.is-disabled::before {
  content: '已禁用';
  position: absolute;
  top: 8px;
  right: 8px;
  padding: 2px 8px;
  background: var(--el-text-color-secondary);
  color: white;
  font-size: 12px;
  border-radius: 4px;
  z-index: 1;
}

.node-block.is-disabled:hover {
  border-color: var(--el-border-color);
  box-shadow: none;
}

.node-block.is-disabled .node-variable,
.node-block.is-disabled .node-type,
.node-block.is-disabled .param-label,
.node-block.is-disabled .param-value {
  color: var(--el-text-color-secondary);
}

.node-block-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.node-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.node-variable {
  font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.node-type {
  font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
  font-size: 14px;
  color: var(--el-text-color-regular);
}

.node-actions {
  display: flex;
  gap: 4px;
}

.node-params {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
  font-size: 13px;
  margin-bottom: 8px;
}

.params-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.params-title {
  font-weight: 600;
  color: var(--el-text-color-regular);
  font-size: 12px;
  text-transform: uppercase;
}

.param-item {
  display: flex;
  gap: 8px;
}

.param-key {
  color: var(--el-text-color-secondary);
  min-width: 120px;
}


.param-value-wrapper {
  flex: 1;
  display: flex;
  align-items: center;
}

.param-value {
  color: var(--el-text-color-primary);
  flex: 1;
  word-break: break-all;
}

.param-value.editable {
  cursor: text;
  border-bottom: 1px dashed transparent;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 6px;
}

.param-value.editable:hover {
  background-color: var(--el-color-primary-light-9);
  border-bottom-color: var(--el-color-primary);
  padding-left: 4px;
  border-radius: 2px;
}

.edit-icon {
  display: none;
  font-size: 12px;
  color: var(--el-color-primary);
}

.param-value.editable:hover .edit-icon {
  display: inline-flex;
}

.add-param-hint {
  padding: 8px 0;
  text-align: center;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.add-param-hint .el-button {
  color: var(--el-color-primary);
}

.node-outputs {
  padding: 12px;
  background: var(--el-color-primary-light-9);
  border-radius: 4px;
  margin-top: 8px;
}

.outputs-title {
  font-weight: 600;
  color: var(--el-text-color-regular);
  margin-bottom: 8px;
  font-size: 12px;
  text-transform: uppercase;
}

.output-items {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.output-tag {
  font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
  cursor: pointer;
}

.output-tag:hover {
  opacity: 0.8;
}

.node-status {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 12px;
  padding: 8px 12px;
  border-radius: 4px;
  font-size: 13px;
}

.status-running {
  background: var(--el-color-info-light-9);
  color: var(--el-color-info);
}

.status-completed {
  background: var(--el-color-success-light-9);
  color: var(--el-color-success);
}

.status-error {
  background: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
}

.add-node-block {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 24px;
  background: var(--el-bg-color);
  border: 2px dashed var(--el-border-color);
  border-radius: 8px;
  cursor: pointer;
  color: var(--el-text-color-secondary);
  transition: all 0.3s;
}

.add-node-block:hover {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
}
</style>
