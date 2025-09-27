<template>
  <div class="tags-editor">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>作品标签设定</span>
          <div>
            <el-button type="primary" @click="handleRandomize">一键随机灵感</el-button>
            <el-button type="success" :loading="isSaving" @click="saveTags">保存更改</el-button>
          </div>
        </div>
      </template>
      <div class="tag-selection-container">
        <el-scrollbar>
          <div class="category-block">
            <div class="category-header">
              <h3>主题标签 (单选)</h3>
              <el-button @click="randomizeTheme" type="primary" plain size="small">随机灵感</el-button>
            </div>
            <el-cascader
              :model-value="themeArray"
              @change="handleThemeChange"
              :options="themeOptions"
              placeholder="请选择小说主题"
              style="width: 100%"
            />
          </div>

          <div class="category-block">
            <div class="category-header">
              <h3>目标读者</h3>
              <el-button @click="randomizeAudience" type="primary" plain size="small">随机灵感</el-button>
            </div>
            <el-radio-group v-model="localData.audience">
              <el-radio v-for="opt in audienceOptions" :key="opt" :value="opt" border>{{ opt }}</el-radio>
            </el-radio-group>
          </div>

          <div class="category-block">
            <div class="category-header">
              <h3>写作人称</h3>
              <el-button @click="randomizePerson" type="primary" plain size="small">随机灵感</el-button>
            </div>
            <el-radio-group v-model="localData.narrative_person">
              <el-radio v-for="opt in personOptions" :key="opt" :value="opt" border>{{ opt }}</el-radio>
            </el-radio-group>
          </div>

          <div class="category-block">
            <div class="category-header">
              <h3>类别标签 (建议选择 3-5 个)</h3>
              <el-button @click="randomizeStoryTags" type="primary" plain size="small">随机灵感</el-button>
            </div>
            <div class="story-tags-grid">
              <div v-for="full in categoryOptions" :key="full" class="story-tag-item">
                <el-checkbox
                  :model-value="isStoryTagSelected(full)"
                  @change="(checked) => handleStoryTagChange(checked, full)"
                >
                  {{ stripAnnotation(full) }}
                </el-checkbox>
                <el-select
                  v-if="isStoryTagSelected(full)"
                  :model-value="getStoryTagWeight(full)"
                  @change="(weight) => updateStoryTagWeight(full, weight as WeightLevel)"
                  size="small"
                  class="weight-input"
                  placeholder="权重"
                >
                  <el-option v-for="w in WEIGHT_LEVELS" :key="w" :label="w" :value="w" />
                </el-select>
              </div>
            </div>
          </div>

          <div class="category-block">
            <div class="category-header">
              <h3>情感关系</h3>
              <el-button @click="randomizeRelationship" type="primary" plain size="small">随机灵感</el-button>
            </div>
                          <el-radio-group v-model="localData.affection">
                <el-radio v-for="tag in relationshipOptions" :key="tag" :value="tag" border>{{ tag }}</el-radio>
              </el-radio-group>
          </div>
        </el-scrollbar>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, watch, computed } from 'vue'
import { ElCard, ElButton } from 'element-plus'
import type { components } from '@renderer/types/generated'
import { useCardStore } from '@renderer/stores/useCardStore'
import { ElMessage } from 'element-plus'
// 引入原子组件
import { 
  ElCheckbox,
  ElRadio,
  ElRadioGroup,
  ElCascader,
  ElScrollbar,
  ElSelect,
  ElOption
} from 'element-plus'
import { onMounted } from 'vue'
import { listKnowledge } from '@renderer/api/setting'
// Define types from generated schemas
type CardRead = components['schemas']['CardRead']
type Tags = components['schemas']['Tags']
type WeightLevel = '低权重' | '中权重' | '高权重'
// 权重档位常量，统一来源
const WEIGHT_LEVELS: WeightLevel[] = ['低权重', '中权重', '高权重']
const DEFAULT_WEIGHT: WeightLevel = '中权重'

const props = defineProps<{
  card: CardRead
}>()

const cardStore = useCardStore()
const isSaving = ref(false)

// 本地可编辑数据
const localData = reactive<Tags>({
  theme: '',
  audience: '男频' as any,
  narrative_person: '第三人称' as any,
  story_tags: [],
  affection: ''
})
// 选项数据（运行时从知识库解析填充）
const themeOptions = ref<any[]>([])
const categoryOptions = ref<string[]>([])
const relationshipOptions = ref<string[]>([])
const audienceOptions = ref<string[]>([])
const personOptions = ref<string[]>([])

watch(
  () => props.card,
  (newCard) => {
    // 确保 content 是对象后再赋值
    if (newCard && newCard.content && typeof newCard.content === 'object') {
      Object.assign(localData, newCard.content as unknown as Partial<Tags>)
    }
  },
  { deep: true, immediate: true }
)

// 随机化入口
const handleRandomize = () => {
  randomizeAll()
}

// 保存
const saveTags = async () => {
  isSaving.value = true
  try {
    await cardStore.modifyCard(props.card.id, { content: localData });
    ElMessage.success('已保存标签设置')
  } catch (error) {
    // 错误消息已在 store 处理
  } finally {
    isSaving.value = false
  }
}

// 主题联动
const themeArray = computed(() => {
  return localData.theme ? localData.theme.split('-') : []
})

function handleThemeChange(value: any) {
  if (Array.isArray(value)) {
    localData.theme = (value as string[]).join('-')
  }
}

// 类别标签逻辑
function isStoryTagSelected(tagName: string) {
  return localData.story_tags.some(([name]) => name === tagName)
}

function getStoryTagWeight(tagName: string): WeightLevel {
  const tag = localData.story_tags.find(([name]) => name === tagName)
  return (tag ? (tag[1] as WeightLevel) : DEFAULT_WEIGHT)
}

function handleStoryTagChange(checked: any, tagName: string) {
  const index = localData.story_tags.findIndex(([name]) => name === tagName)
  if (checked as boolean) {
    if (index === -1) {
      localData.story_tags.push([tagName, DEFAULT_WEIGHT as any])
    }
  } else {
    if (index !== -1) {
      localData.story_tags.splice(index, 1)
    }
  }
}

function updateStoryTagWeight(tagName: string, weight: WeightLevel | undefined) {
  const tag = localData.story_tags.find(([name]) => name === tagName)
  if (tag && typeof weight === 'string') {
    tag[1] = weight
  }
}

// 随机化
function randomizeAll() {
  randomizeTheme()
  randomizeAudience()
  randomizePerson()
  randomizeStoryTags()
  randomizeRelationship()
}

function randomizeTheme() {
  if (!themeOptions.value.length) return
  const mainTheme = themeOptions.value[Math.floor(Math.random() * themeOptions.value.length)]
  const subTheme = mainTheme.children[Math.floor(Math.random() * mainTheme.children.length)]
  localData.theme = `${mainTheme.value}-${subTheme.value}`
}

function randomizeStoryTags() {
  const count = Math.floor(Math.random() * 3) + 3 // 3 到 5 个
  const shuffled = [...categoryOptions.value].sort(() => 0.5 - Math.random())
  localData.story_tags = shuffled.slice(0, count).map(tag => {
    const weight = WEIGHT_LEVELS[Math.floor(Math.random() * WEIGHT_LEVELS.length)]
    return [tag, weight as any]
  })
}

function randomizeRelationship() {
  if (!relationshipOptions.value.length) return
  localData.affection = relationshipOptions.value[Math.floor(Math.random() * relationshipOptions.value.length)]
}

function randomizeAudience() {
  if (!audienceOptions.value.length) return
  localData.audience = audienceOptions.value[Math.floor(Math.random() * audienceOptions.value.length)] as any
}

function randomizePerson() {
  if (!personOptions.value.length) return
  localData.narrative_person = personOptions.value[Math.floor(Math.random() * personOptions.value.length)] as any
}

// 知识库解析：仅渲染名称；story_tags 存储完整项
function stripAnnotation(label: string): string {
  // 去除括号中的注解（中文/英文括号）
  return label.replace(/\s*[（(].*[）)]\s*$/, '')
}

function parseKnowledge(text: string) {
  // 去除围栏与空白行
  const rawLines = (text || '').split(/\r?\n/)
  const lines: string[] = []
  for (const l of rawLines) {
    const t = l.replace(/\t/g, '    ')
    if (!t.trim().length) continue
    if (t.trim() === '```') continue
    lines.push(t)
  }
  type Section = 'none' | 'theme' | 'audience' | 'person' | 'category' | 'affection'
  let section: Section = 'none'
  const themes: Record<string, string[]> = {}
  let currentTheme: string | null = null
  const categories: string[] = []
  const relationships: string[] = []
  const audiences: string[] = []
  const persons: string[] = []

  for (const raw of lines) {
    const m = raw.match(/^(\s*)-\s*(.+)$/)
    if (!m) continue
    const indent = m[1].length
    const content = m[2].trim()

    // 切换段落
    if (indent <= 2) {
      if (content.startsWith('主题标签')) { section = 'theme'; currentTheme = null; continue }
      if (content.startsWith('目标群体')) { section = 'audience'; continue }
      if (content.startsWith('写作人称')) { section = 'person'; continue }
      if (content.startsWith('类别标签')) { section = 'category'; continue }
      if (content.startsWith('情感关系')) { section = 'affection'; continue }
    }

    if (section === 'theme') {
      const ROOT_INDENT_MAX = 6
      if (indent <= ROOT_INDENT_MAX || !currentTheme) {
        const name = stripAnnotation(content)
        if (!themes[name]) themes[name] = []
        currentTheme = name
      } else {
        const sub = stripAnnotation(content)
        if (!currentTheme) {
          const fallback = stripAnnotation(content)
          themes[fallback] = []
          currentTheme = fallback
        } else {
          themes[currentTheme].push(sub)
        }
      }
      continue
    }

    if (section === 'audience') {
      const name = stripAnnotation(content)
      if (name) audiences.push(name)
      continue
    }
    if (section === 'person') {
      const name = stripAnnotation(content)
      if (name) persons.push(name)
      continue
    }
    if (section === 'category') {
      // 类别：保留完整字符串（含注解）
      categories.push(content)
      continue
    }
    if (section === 'affection') {
      const name = stripAnnotation(content)
      if (name) relationships.push(name)
      continue
    }
  }

  themeOptions.value = Object.keys(themes).map(k => ({ value: k, label: k, children: (themes[k] || []).map(s => ({ value: s, label: s })) }))
  categoryOptions.value = categories
  relationshipOptions.value = relationships
  audienceOptions.value = audiences.length ? audiences : ['男频','女频']
  personOptions.value = persons.length ? persons : ['第一人称','第三人称']
}

onMounted(async () => {
  try {
    const list = await listKnowledge()
    const kb = (list || []).find(k => k && k.name === '作品标签')
    if (kb && kb.content) parseKnowledge(kb.content)
  } catch {}
})
// ----------------- 合并逻辑结束 -----------------
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

/* 原 Step0TagSelection 样式 */
.tag-selection-container {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.category-block {
  margin-bottom: 24px;
}
.category-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.category-block h3 {
  margin-bottom: 0;
  font-size: 1.1em;
  font-weight: 600;
  border-left: 4px solid var(--el-color-primary);
  padding-left: 8px;
  color: var(--text-color-primary);
}

.story-tags-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 15px;
}

.story-tag-item {
  display: flex;
  align-items: center;
  gap: 10px;
}

.weight-input {
  width: 70px;
}

.el-radio-group {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.el-radio.is-bordered {
  margin: 0;
}
</style> 