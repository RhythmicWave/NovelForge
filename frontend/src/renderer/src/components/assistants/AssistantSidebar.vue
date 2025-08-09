<script setup lang="ts">
import { computed, ref } from 'vue'
import type { components } from '@renderer/types/generated'
import { ElScrollbar, ElCard, ElAlert, ElIcon } from 'element-plus'
import { MagicStick, Compass, View } from '@element-plus/icons-vue'
import type { AIGenerationConfig } from '@renderer/api/ai'

// --- 类型定义 ---
interface ProjectData {
  volumes: (components['schemas']['VolumeRead'] & {
    chapters: (components['schemas']['ChapterRead'] & { outline?: any })[] // 为Chapter添加outline
    outline?: any
  })[]
}

const props = defineProps<{
  projectData: ProjectData | null
  activeEditor: { type: string; id: string; data?: any } | null
  project: any
}>()

const emit = defineEmits<{
  'ai-generate': [config: AIGenerationConfig]
}>()

// --- 侧边栏状态管理 ---
const activeTool = ref('outline-inspector') // 默认激活"大纲速查"
const tools = [
  { id: 'ai-assistant', label: 'AI助手', icon: MagicStick },
  { id: 'outline-inspector', label: '大纲速查', icon: Compass },
  { id: 'context-injection', label: '信息注入', icon: View }
]

// --- 计算属性 ---
// 计算当前任务类型
const currentTask = computed(() => {
  if (!props.activeEditor) return undefined
  
  const taskMap: Record<string, string> = {
    'synopsis': 'core-idea',
    'world-building': 'world-building',
    'blueprint': 'blueprint',
    'volume-outline': 'volume-outline',
    'chapter-outline': 'chapter-outline'
  }
  
  return taskMap[props.activeEditor.type]
})

// 计算属性，用于动态获取当前章节所属分卷的大纲
const currentVolumeInfo = computed(() => {
  if (!props.activeEditor || !props.projectData) {
    return null
  }
  
  let volumeId: number | null = null
  
  // 根据不同的编辑器类型获取分卷ID
  if (props.activeEditor.type === 'chapter-content') {
    // 从章节ID中提取分卷ID
    const chapterId = Number(props.activeEditor.id.replace('chap-', ''))
    // 通过查找章节所属的分卷来确定volume_id
    for (const volume of props.projectData.volumes) {
      const chapter = volume.chapters.find(c => c.id === chapterId)
      if (chapter) {
        volumeId = volume.id
        break
      }
    }
  } else if (props.activeEditor.type === 'volume-outline') {
    // 从分卷大纲ID中提取分卷ID
    volumeId = Number(props.activeEditor.id.replace('vol-', ''))
  }
  
  if (!volumeId) return null
  
  const volume = props.projectData.volumes.find((v) => v.id === volumeId)
  if (!volume) return null
  

  
  return {
    id: volume.id,
    title: volume.title,
    description: volume.description || '暂无分卷描述',
    outline: volume.outline || null
  }
})

// 查找章节信息的辅助函数
function findChapterById(chapterId: number) {
  for (const volume of props.projectData?.volumes || []) {
    const chapter = volume.chapters.find(c => c.id === chapterId)
    if (chapter) return chapter
  }
  return null
}

// 获取当前章节信息
const currentChapter = computed(() => {
  if (props.activeEditor?.type !== 'chapter-content') return null
  
  const chapterId = Number(props.activeEditor.id.replace('chap-', ''))
  const chapter = findChapterById(chapterId)
  
  return chapter
})

// 获取相关的阶段性故事线
const relevantStageLines = computed(() => {
  if (!currentVolumeInfo.value?.outline || !currentChapter.value) return []
  
  const outline = currentVolumeInfo.value.outline
  // 从章节标题中提取章节号
  const chapterTitle = currentChapter.value.title || ''
  const chapterMatch = chapterTitle.match(/^第(\d+)章/)
  const currentChapterNumber = chapterMatch ? parseInt(chapterMatch[1]) : currentChapter.value.id
  
  // 筛选出当前章节范围内的阶段性故事线
  return (outline.stage_lines || []).filter((stageLine: any) => {
    if (!stageLine.reference_chapter) {
      return false
    }
    
    const refChapter = stageLine.reference_chapter
    // reference_chapter是一个元组 [start, end]
    const startChapter = Array.isArray(refChapter) ? refChapter[0] : 1
    const endChapter = Array.isArray(refChapter) ? refChapter[1] : 999
    
    return currentChapterNumber >= startChapter && currentChapterNumber <= endChapter
  })
})

// 处理AI生成
function handleAIGenerate(config: AIGenerationConfig) {
  emit('ai-generate', config)
}
</script>

<template>
  <div class="assistant-container">
    <!-- 内容面板 -->
    <div class="content-panel">
      <el-scrollbar>
        <!-- AI助手 面板 -->
        <div v-if="activeTool === 'ai-assistant'" class="panel-content placeholder">
          <p>AI 助手聊天界面（待实现）</p>
        </div>

        <!-- 大纲速查 面板 -->
        <div v-else-if="activeTool === 'outline-inspector'" class="panel-content">
          <!-- 优先显示章节大纲 -->
          <div v-if="currentChapter?.outline">
            <el-card class="outline-card chapter-outline-card">
              <template #header>
                <div class="outline-header">
                  <span>{{ currentChapter.title }} - 章节大纲</span>
                  <el-tag size="small">
                    第{{ currentChapter.outline.chapter_number }}章
                  </el-tag>
                </div>
              </template>
              
              <div class="outline-section">
                <h4 class="section-title">📝 章节概述</h4>
                <p class="overview-content">{{ currentChapter.outline.overview }}</p>
              </div>

              <div v-if="currentChapter.outline.enemy" class="outline-section">
                <h4 class="section-title">⚔️ 新增敌人</h4>
                <p><strong>名称：</strong> {{ currentChapter.outline.enemy.name }}</p>
                <p><strong>描述：</strong> {{ currentChapter.outline.enemy.description }}</p>
              </div>

              <div v-if="currentChapter.outline.resolve_enemy" class="outline-section">
                <h4 class="section-title">✅ 解决冲突</h4>
                <p><strong>目标：</strong> {{ currentChapter.outline.resolve_enemy.resolve_name }} (来自第{{ currentChapter.outline.resolve_enemy.resolve_id }}章)</p>
                <p><strong>解决方式：</strong> {{ currentChapter.outline.resolve_enemy.description }}</p>
              </div>

            </el-card>
          </div>
          
          <!-- 否则，显示分卷大纲 -->
          <div v-else-if="currentVolumeInfo">
            <el-card class="outline-card">
              <template #header>
                <div class="outline-header">
                  <span>{{ currentVolumeInfo.title }} - 大纲速查</span>
                  <el-tag v-if="currentChapter" size="small" type="info">
                    当前：第{{ currentChapter.id }}章
                  </el-tag>
                </div>
              </template>
              
              <!-- 主线目标 -->
              <div v-if="currentVolumeInfo.outline?.main_target" class="outline-section">
                <h4 class="section-title">🎯 主线目标</h4>
                <div class="target-content">
                  <p><strong>类型：</strong>{{ currentVolumeInfo.outline.main_target.story_type || '主线' }}</p>
                  <p><strong>名称：</strong>{{ currentVolumeInfo.outline.main_target.name || '未设置' }}</p>
                  <p><strong>概述：</strong>{{ currentVolumeInfo.outline.main_target.overview || '暂无概述' }}</p>
                </div>
              </div>

              <!-- 支线剧情 -->
              <div v-if="currentVolumeInfo.outline?.branch_line && currentVolumeInfo.outline.branch_line.length > 0" class="outline-section">
                <h4 class="section-title">🌿 支线剧情</h4>
                <div v-for="(branch, index) in currentVolumeInfo.outline.branch_line" :key="index" class="branch-item">
                  <p><strong>{{ branch.name || `支线${index + 1}` }}：</strong>{{ branch.overview || '暂无概述' }}</p>
                </div>
              </div>

              <!-- 阶段性故事线 -->
              <div v-if="relevantStageLines.length > 0" class="outline-section">
                <h4 class="section-title">📖 阶段性故事线</h4>
                <div v-for="(stageLine, index) in relevantStageLines" :key="index" class="stage-line-item">
                  <div class="stage-line-header">
                    <span class="stage-line-name">{{ stageLine.stage_name || `阶段${index + 1}` }}</span>
                    <el-tag v-if="stageLine.reference_chapter" size="small" type="warning">
                      第{{ Array.isArray(stageLine.reference_chapter) ? stageLine.reference_chapter[0] : 1 }}-{{ Array.isArray(stageLine.reference_chapter) ? stageLine.reference_chapter[1] : 1 }}章
                    </el-tag>
                  </div>
                  <p class="stage-line-overview">{{ stageLine.overview || '暂无概述' }}</p>
                  <div v-if="stageLine.analysis" class="stage-analysis">
                    <p class="analysis-title"><strong>创作分析：</strong></p>
                    <p class="analysis-content">{{ stageLine.analysis }}</p>
                  </div>
                </div>
              </div>

              <!-- 创作思考 -->
              <div v-if="currentVolumeInfo.outline?.thinking" class="outline-section">
                <h4 class="section-title">💭 创作思考</h4>
                <p class="thinking-content">{{ currentVolumeInfo.outline.thinking }}</p>
              </div>

              <!-- 无大纲数据时的提示 -->
              <div v-if="!currentVolumeInfo.outline" class="no-outline">
                <el-alert title="暂无大纲数据" type="info" :closable="false">
                  <p>该分卷尚未设置大纲，请先在分卷大纲编辑器中设置主线和支线内容。</p>
                </el-alert>
              </div>
            </el-card>
          </div>
          <div v-else class="placeholder">
            <p>选择一个章节进行编辑，此处将显示该章节所属分卷的大纲。</p>
          </div>
        </div>

        <!-- 信息注入 面板 -->
        <div v-else-if="activeTool === 'context-injection'" class="panel-content placeholder">
          <p>AI 调用上下文信息（待实现）</p>
        </div>


      </el-scrollbar>
    </div>

    <!-- 垂直活动栏 -->
    <div class="activity-bar">
      <button
        v-for="tool in tools"
        :key="tool.id"
        :class="['tool-button', { active: activeTool === tool.id }]"
        @click="activeTool = tool.id"
        :title="tool.label"
      >
        <el-icon :size="24"><component :is="tool.icon" /></el-icon>
        <span class="tool-label">{{ tool.label }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
/* 样式与之前相同，保持活动栏布局 */
.assistant-container {
  display: flex;
  flex-direction: row;
  height: 100%;
  width: 100%;
  overflow: hidden;
}

.content-panel {
  flex-grow: 1;
  height: 100%;
  overflow-y: auto;
}

.panel-content {
  padding: 15px;
}

.activity-bar {
  width: 80px;
  flex-shrink: 0;
  height: 100%;
  background-color: var(--el-bg-color-page);
  border-left: 1px solid var(--el-border-color-light);
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 15px 0; /* 调整内边距，移除顶部间距，改为上下内边距 */
  gap: 15px;
}

.tool-button {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 60px;
  height: 60px;
  border-radius: 8px;
  border: 1px solid transparent;
  background-color: transparent;
  cursor: pointer;
  color: var(--el-text-color-regular);
  transition: all 0.2s ease;
}

.tool-button:hover {
  background-color: var(--el-fill-color-light);
  color: var(--el-color-primary);
}

.tool-button.active {
  background-color: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  border-color: var(--el-color-primary-light-5);
}

.tool-label {
  font-size: 12px;
  margin-top: 4px;
  white-space: nowrap; /* 防止文字换行 */
}

.placeholder {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100%;
  color: var(--el-text-color-secondary);
  text-align: center;
  padding: 20px;
  box-sizing: border-box;
}

/* 大纲速查样式 */
.outline-card {
  margin-bottom: 15px;
}

.outline-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.outline-section {
  margin-bottom: 20px;
  padding-bottom: 15px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.outline-section:last-child {
  border-bottom: none;
  margin-bottom: 0;
}

.section-title {
  margin: 0 0 10px 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.target-content p,
.branch-item p,
.stage-line-overview {
  margin: 5px 0;
  font-size: 13px;
  line-height: 1.5;
  color: var(--el-text-color-regular);
}

.branch-item {
  margin-bottom: 8px;
  padding: 8px;
  background-color: var(--el-fill-color-lighter);
  border-radius: 4px;
}

.stage-line-item {
  margin-bottom: 15px;
  padding: 12px;
  background-color: var(--el-fill-color-lighter);
  border-radius: 6px;
  border-left: 3px solid var(--el-color-primary);
}

.stage-line-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.stage-line-name {
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.stage-line-overview {
  margin: 8px 0;
  font-size: 13px;
  color: var(--el-text-color-regular);
}

.story-points {
  margin-top: 10px;
}

.story-points-title {
  margin: 0 0 5px 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
}

.story-points-list {
  margin: 0;
  padding-left: 15px;
}

.story-points-list li {
  font-size: 12px;
  color: var(--el-text-color-regular);
  margin-bottom: 3px;
}

.stage-analysis {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.analysis-title {
  margin: 0 0 5px 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
}

.analysis-content {
  font-size: 12px;
  color: var(--el-text-color-regular);
  line-height: 1.4;
  font-style: italic;
}

.thinking-content {
  font-size: 13px;
  line-height: 1.6;
  color: var(--el-text-color-regular);
  font-style: italic;
}

.no-outline {
  margin-top: 15px;
}

/* 章节大纲特有样式 */
.chapter-outline-card {
  border-left: 3px solid var(--el-color-success);
}

.overview-content {
  font-size: 14px;
  line-height: 1.6;
}

</style> 