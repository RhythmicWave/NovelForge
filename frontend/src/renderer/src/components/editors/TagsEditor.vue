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
      <!-- 合并原 Step0TagSelection 的内容 -->
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
              <h3>类别标签 (建议选择 3-5 个)</h3>
              <el-button @click="randomizeStoryTags" type="primary" plain size="small">随机灵感</el-button>
            </div>
            <div class="story-tags-grid">
              <div v-for="tag in categoryOptions" :key="tag" class="story-tag-item">
                <el-checkbox
                  :model-value="isStoryTagSelected(tag)"
                  @change="(checked) => handleStoryTagChange(checked, tag)"
                >
                  {{ tag }}
                </el-checkbox>
                <el-input-number
                  v-if="isStoryTagSelected(tag)"
                  :model-value="getStoryTagWeight(tag)"
                  @change="(weight) => updateStoryTagWeight(tag, weight)"
                  :min="0.4"
                  :max="1.0"
                  :step="0.1"
                  :controls="false"
                  size="small"
                  class="weight-input"
                />
              </div>
            </div>
          </div>

          <div class="category-block">
            <div class="category-header">
              <h3>情感关系 (单选)</h3>
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
// 移除子组件引用，直接在本组件内实现
// import Step0TagSelection from '@renderer/components/common/Step0TagSelection.vue'
import type { components } from '@renderer/types/generated'
import { useCardStore } from '@renderer/stores/useCardStore'
import { ElMessage } from 'element-plus'
// 引入原子组件（若项目有自动按需引入可省略，但显式导入更清晰）
import { 
  ElCheckbox,
  ElRadio,
  ElRadioGroup,
  ElCascader,
  ElScrollbar,
  ElInputNumber
} from 'element-plus'

// Define types from generated schemas
type CardRead = components['schemas']['CardRead']
type Tags = components['schemas']['Tags']

const props = defineProps<{
  card: CardRead
}>()

const cardStore = useCardStore()
const isSaving = ref(false)

// 本地可编辑数据
const localData = reactive<Tags>({
  theme: '',
  story_tags: [],
  affection: ''
})

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

// 随机化入口（合并后直接调用本地函数）
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

// ----------------- 以下为原 Step0TagSelection 的逻辑（合并） -----------------
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

function getStoryTagWeight(tagName: string) {
  const tag = localData.story_tags.find(([name]) => name === tagName)
  return tag ? tag[1] : 1.0
}

function handleStoryTagChange(checked: any, tagName: string) {
  const index = localData.story_tags.findIndex(([name]) => name === tagName)
  if (checked as boolean) {
    if (index === -1) {
      localData.story_tags.push([tagName, 1.0])
    }
  } else {
    if (index !== -1) {
      localData.story_tags.splice(index, 1)
    }
  }
}

function updateStoryTagWeight(tagName: string, weight: number | undefined) {
  const tag = localData.story_tags.find(([name]) => name === tagName)
  if (tag && typeof weight === 'number') {
    tag[1] = weight
  }
}

// 随机化
function randomizeAll() {
  randomizeTheme()
  randomizeStoryTags()
  randomizeRelationship()
}

function randomizeTheme() {
  const mainTheme = themeOptions[Math.floor(Math.random() * themeOptions.length)]
  const subTheme = mainTheme.children[Math.floor(Math.random() * mainTheme.children.length)]
  localData.theme = `${mainTheme.value}-${subTheme.value}`
}

function randomizeStoryTags() {
  const count = Math.floor(Math.random() * 3) + 3 // 3 到 5 个
  const shuffled = [...categoryOptions].sort(() => 0.5 - Math.random())
  localData.story_tags = shuffled.slice(0, count).map(tag => {
    const weight = Math.random() * (1.0 - 0.4) + 0.4
    return [tag, parseFloat(weight.toFixed(2))]
  })
}

function randomizeRelationship() {
  localData.affection = relationshipOptions[Math.floor(Math.random() * relationshipOptions.length)]
}

// 选项数据（来自原 tags 列表）
const themeOptions = [
  { value: '玄幻奇幻', label: '玄幻奇幻', children: [
      { value: '东方玄幻', label: '东方玄幻' }, { value: '异世大陆', label: '异世大陆' },
      { value: '高武世界', label: '高武世界' }, { value: '王朝争霸', label: '王朝争霸' }, { value: '西方奇幻', label: '西方奇幻' }
  ]},
  { value: '科幻', label: '科幻', children: [
      { value: '星际文明', label: '星际文明' }, { value: '机甲古武', label: '机甲古武' },
      { value: '末世危机', label: '末世危机' }, { value: '时空穿越', label: '时空穿越' }
  ]},
  { value: '武侠仙侠', label: '武侠仙侠', children: [
      { value: '古典仙侠', label: '古典仙侠' }, { value: '修真文明', label: '修真文明' },
      { value: '洪荒封神', label: '洪荒封神' }, { value: '幻想修仙', label: '幻想修仙' },
      { value: '传统武侠', label: '传统武侠' }, { value: '幻想武侠', label: '幻想武侠' }
  ]},
  { value: '都市', label: '都市', children: [
      { value: '都市高武', label: '都市高武' }, { value: '商战风云', label: '商战风云' },
      { value: '娱乐明星', label: '娱乐明星' }, { value: '乡村生活', label: '乡村生活' }, { value: '风水相师', label: '风水相师' }
  ]},
  { value: '历史', label: '历史', children: [
      { value: '架空历史', label: '架空历史' }, { value: '历史穿越', label: '历史穿越' }, { value: '工业革命', label: '工业革命' }
  ]},
  { value: '游戏', label: '游戏', children: [
      { value: '全息网游', label: '全息网游' }, { value: '游戏异界', label: '游戏异界' }, { value: '数据化身', label: '数据化身' }
  ]},
  { value: '悬疑', label: '悬疑', children: [
      { value: '侦探推理', label: '侦探推理' }, { value: '诡异怪谈', label: '诡异怪谈' },
      { value: '盗墓探险', label: '盗墓探险' }, { value: '规则怪谈', label: '规则怪谈' }
  ]}
]
const categoryOptions = ['穿越', '重生', '反穿', '系统流', '直播', '权谋', '种田流', '迪化', '灵气复苏', '异界科学流', '废柴流', '学霸流', '无敌流', '扮猪吃老虎', '稳健流', '金手指批发', '幕后流', '时间回溯/预知未来', '第四天灾', '诡异修仙', '模拟器', '文抄公', '诸天穿梭', '文明推演', '反派洗白', '群聊互动', '签到流', '加点流', '反派流', '操控流', '成神流', '无限流', '双向穿越', '偷听流', '收徒流', '文明碰撞', '唯一超凡', '异界修炼体系降维打击', '末日求生', '诡异副本', '轮回流', '诡秘流', '规则怪谈', '现实穿插', '反转流', '失控流', '进化流', '失落文明', '娱乐圈', '校园', '灵异', '召唤流', '奶爸', '神豪', '乡村', '异兽流', '老师', '特工', '神医', '轻松']
const relationshipOptions = ['无CP', '单女主', '多女主', '纯爱', '青梅竹马']
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