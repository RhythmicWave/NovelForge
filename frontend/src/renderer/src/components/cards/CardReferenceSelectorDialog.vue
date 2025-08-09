<template>
  <el-dialog
    :model-value="modelValue"
    title="引用卡片/上下文"
    width="70%"
    @update:modelValue="$emit('update:modelValue', $event)"
    @close="reset"
  >
    <div class="selector-container">
      <!-- 左列：模式选择 + 列表区 -->
      <div class="column left">
        <h3>1. 选择引用方式</h3>
        <el-radio-group v-model="mode" size="small">
          <el-radio-button label="title">按标题</el-radio-button>
          <el-radio-button label="type">按类型</el-radio-button>
          <el-radio-button label="special">特殊</el-radio-button>
        </el-radio-group>

        <!-- 按标题模式：原有卡片列表 -->
        <template v-if="mode === 'title'">
          <el-input v-model="cardSearch" placeholder="搜索卡片..." clearable class="mt8" />
          <el-scrollbar class="list-container">
            <ul class="card-list">
              <li
                v-for="card in filteredCards"
                :key="card.id"
                :class="{ selected: selectedKard?.id === card.id }"
                @click="handleCardSelect(card)"
              >
                {{ card.title }}
              </li>
            </ul>
          </el-scrollbar>
        </template>

        <!-- 按类型模式：类型下拉 + index 表达式 -->
        <template v-else-if="mode === 'type'">
          <div class="mt8">
            <el-select v-model="selectedTypeName" placeholder="选择卡片类型" style="width: 100%" @change="handleTypeChange">
              <el-option v-for="t in cardTypeNames" :key="t" :label="t" :value="t" />
            </el-select>
          </div>
          <div class="mt8">
            <el-input v-model="indexExpr" placeholder="index= 的表达式，例如 last / 1 / $current.volumeNumber-1" />
          </div>
        </template>

        <!-- 特殊模式：self / parent / stage:current / chapters:previous -->
        <template v-else>
          <div class="mt8">
            <el-select v-model="specialKey" placeholder="选择特殊引用" style="width: 100%">
              <el-option label="self（当前卡片）" value="self" />
              <el-option label="parent（父卡片）" value="parent" />
              <el-option label="stage:current（当前阶段）" value="stage:current" />
              <el-option label="chapters:previous（之前章节列表）" value="chapters:previous" />
            </el-select>
          </div>
          <div class="mt8" v-if="specialKey === 'self' || specialKey === 'parent' || specialKey === 'stage:current'">
            <el-input v-model="specialPath" placeholder="可选：在此输入字段路径，如 content.volume_outline.main_target" />
          </div>
        </template>
      </div>

      <!-- 右列：字段树 -->
      <div class="column">
        <h3>2. 选择字段（可选）</h3>
        <el-tree
          v-if="fieldPaths.length"
          :data="fieldPaths"
          :props="{ label: 'label', children: 'children' }"
          @node-click="handleFieldSelect"
          class="field-tree"
          highlight-current
        />
        <div v-else class="empty-state">
          <p>在此选择要追加的字段路径（可选）。</p>
        </div>
      </div>
    </div>

    <!-- Footer -->
    <template #footer>
      <div class="footer-container">
        <span class="selection-preview">
          预览: <strong>{{ selectionPreview }}</strong>
        </span>
        <span class="dialog-footer">
          <el-button @click="$emit('update:modelValue', false)">取消</el-button>
          <el-button type="primary" @click="handleConfirm" :disabled="!canConfirm">
            确认
          </el-button>
        </span>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { CardRead } from '@renderer/api/cards'
import { schemaService, type JSONSchema } from '@renderer/api/schema'
import { ElDialog, ElInput, ElScrollbar, ElTree, ElButton, ElRadioGroup, ElRadioButton, ElSelect, ElOption } from 'element-plus'

interface FieldPath {
  label: string
  path: string
  children?: FieldPath[]
}

const props = defineProps<{ modelValue: boolean; cards: CardRead[] }>()
const emit = defineEmits(['update:modelValue', 'confirm'])

// --- 模式与选择 ---
const mode = ref<'title' | 'type' | 'special'>('title')

// 按标题
const cardSearch = ref('')
const selectedKard = ref<CardRead | null>(null)

// 按类型
const selectedTypeName = ref<string | undefined>(undefined)
const indexExpr = ref<string>('last')

// 特殊
const specialKey = ref<string | undefined>(undefined)
const specialPath = ref<string>('')

// 字段树
const selectedFieldPath = ref<string | null>(null)
const fieldPaths = ref<FieldPath[]>([])

// 过滤卡片（按标题）
const filteredCards = computed(() => props.cards.filter(card => card.title.toLowerCase().includes(cardSearch.value.toLowerCase())))

// 所有类型名
const cardTypeNames = computed(() => Array.from(new Set(props.cards.map(c => c.card_type?.name).filter(Boolean) as string[])))

// 预览字符串
const selectionPreview = computed(() => {
  if (mode.value === 'title') {
    if (!selectedKard.value) return ''
    let s = `@${selectedKard.value.title}`
    if (selectedFieldPath.value) s += `.${selectedFieldPath.value}`
    return s
  }
  if (mode.value === 'type') {
    if (!selectedTypeName.value) return ''
    const idx = indexExpr.value?.trim() ? `[index=${indexExpr.value.trim()}]` : ''
    let s = `@type:${selectedTypeName.value}${idx}`
    if (selectedFieldPath.value) s += `.${selectedFieldPath.value}`
    return s
  }
  if (mode.value === 'special') {
    if (!specialKey.value) return ''
    let s = `@${specialKey.value}`
    if (specialPath.value && specialKey.value !== 'chapters:previous') {
      s += `.${specialPath.value}`
    }
    return s
  }
  return ''
})

const canConfirm = computed(() => {
  if (mode.value === 'title') return !!selectedKard.value
  if (mode.value === 'type') return !!selectedTypeName.value
  if (mode.value === 'special') return !!specialKey.value
  return false
})

watch(
  () => props.modelValue,
  isOpening => {
    if (isOpening) reset()
  }
)

function reset() {
  mode.value = 'title'
  // 标题模式
  cardSearch.value = ''
  selectedKard.value = null
  // 类型模式
  selectedTypeName.value = undefined
  indexExpr.value = 'last'
  // 特殊模式
  specialKey.value = undefined
  specialPath.value = ''
  // 字段树与路径
  selectedFieldPath.value = null
  fieldPaths.value = []
}

async function handleCardSelect(card: CardRead) {
  selectedKard.value = card
  selectedFieldPath.value = null
  fieldPaths.value = []
  const modelName = (card.card_type as any).output_model_name as string | undefined
  if (modelName) {
    await schemaService.loadSchemas()
    const schema = schemaService.getSchema(modelName)
    if (schema) fieldPaths.value = generateFieldPaths(schema)
  }
}

async function handleTypeChange() {
  // 根据类型名选取任意同类型卡片以加载其 schema
  selectedFieldPath.value = null
  fieldPaths.value = []
  const sample = props.cards.find(c => c.card_type?.name === selectedTypeName.value)
  const modelName = (sample?.card_type as any)?.output_model_name as string | undefined
  if (modelName) {
    await schemaService.loadSchemas()
    const schema = schemaService.getSchema(modelName)
    if (schema) fieldPaths.value = generateFieldPaths(schema)
  }
}

function generateFieldPaths(schema: JSONSchema, prefix = 'content'): FieldPath[] {
  const paths: FieldPath[] = []
  if (schema && (schema as any).properties) {
    for (const [key, propSchema] of Object.entries((schema as any).properties)) {
      const currentPath = `${prefix}.${key}`
      const node: FieldPath = {
        label: (propSchema as any).title || key,
        path: currentPath,
      }
      if ((propSchema as any).type === 'object' && (propSchema as any).properties) {
        node.children = generateFieldPaths(propSchema as any, currentPath)
      }
      paths.push(node)
    }
  }
  return paths
}

function handleFieldSelect(data: FieldPath) {
  if (!data.children || data.children.length === 0) {
    selectedFieldPath.value = data.path
  }
}

function handleConfirm() {
  if (selectionPreview.value) {
    emit('confirm', selectionPreview.value)
    emit('update:modelValue', false)
  }
}
</script>

<style scoped>
.selector-container { display: flex; gap: 20px; height: 60vh; border-top: 1px solid var(--el-border-color); border-bottom: 1px solid var(--el-border-color); padding: 10px 0; }
.column { flex: 1; display: flex; flex-direction: column; overflow: hidden; border-right: 1px solid var(--el-border-color); padding-right: 20px; }
.column:last-child { border-right: none; padding-right: 0; }
.column.left { width: 46%; max-width: 520px; }
.list-container { margin-top: 10px; flex-grow: 1; }
.card-list { list-style: none; padding: 0; margin: 0; }
.card-list li { padding: 8px 12px; cursor: pointer; border-radius: 4px; }
.card-list li:hover { background-color: var(--el-fill-color-light); }
.card-list li.selected { background-color: var(--el-color-primary-light-9); color: var(--el-color-primary); font-weight: bold; }
.field-tree { margin-top: 10px; flex-grow: 1; overflow: auto; }
.empty-state { margin-top: 10px; color: var(--el-text-color-secondary); text-align: center; padding-top: 20px; }
.footer-container { display: flex; justify-content: space-between; align-items: center; width: 100%; }
.selection-preview { font-size: 14px; color: var(--el-text-color-secondary); }
.mt8 { margin-top: 8px; }
</style> 