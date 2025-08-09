<template>
  <div class="dashboard-container">
    <!-- 顶部横幅：视觉层级 + 关键信息与CTA -->
    <section class="dashboard-hero">
      <div class="hero-text">
        <h1>我的书架</h1>
        <p class="subtitle">汇聚你的世界与故事，从这里开启每一次灵感</p>
      </div>
      <el-button type="primary" :icon="Plus" @click="handleOpenCreateDialog" size="large" class="hero-cta">
        开始创作
      </el-button>
    </section>

    <!-- 工具条：搜索 + 排序 -->
    <div class="toolbar">
      <el-input v-model="searchQuery" placeholder="搜索项目（按名称/描述包含匹配）" clearable class="search-input" />
      <el-select v-model="sortKey" class="sort-select" size="default">
        <el-option label="按创建时间（最新优先）" value="created-desc" />
        <el-option label="按创建时间（最旧优先）" value="created-asc" />
        <el-option label="按名称 A→Z" value="name-asc" />
        <el-option label="按名称 Z→A" value="name-desc" />
      </el-select>
    </div>

    <main class="dashboard-main" v-loading="isLoading">
      <el-empty v-if="displayProjects.length === 0" description="没有匹配的项目，试试新建一个吧！">
        <el-button type="primary" :icon="Plus" @click="handleOpenCreateDialog">新建项目</el-button>
      </el-empty>
      <el-row :gutter="20" v-else>
        <el-col :xs="24" :sm="12" :md="8" :lg="6" :xl="6" v-for="project in displayProjects" :key="project.id">
          <el-card class="project-card showcase" shadow="hover" @click="handleProjectSelect(project)">
            <!-- 封面：渐变 + 首字母标识，让卡片更有辨识度 -->
            <div class="card-cover" :class="getCoverClass(project.name)">
              <span class="cover-initial">{{ getInitial(project.name) }}</span>
            </div>
            <div class="card-content">
              <div class="title-row">
                <h3 class="title" :title="project.name">{{ project.name }}</h3>
                <!-- 悬浮显隐的操作按钮：避免信息噪点 -->
                <div class="card-actions" @click.stop>
                  <el-tooltip content="编辑"><el-button :icon="Edit" circle plain size="small" @click="handleProjectEdit(project)" /></el-tooltip>
                  <el-tooltip content="删除"><el-button :icon="Delete" circle plain type="danger" size="small" @click="handleProjectDelete(project)" /></el-tooltip>
                </div>
              </div>
              <p class="desc" :title="project.description || '暂无简介'">{{ project.description || '暂无简介' }}</p>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </main>
    <ProjectCreateDialog ref="createDialogRef" @create="handleProjectCreate" @update="handleProjectUpdate" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { ElMessageBox } from 'element-plus'
import { Plus, Delete, Edit } from '@element-plus/icons-vue'
import { storeToRefs } from 'pinia'
import type { components } from '@renderer/types/generated'
import ProjectCreateDialog from '@renderer/components/ProjectCreateDialog.vue'
import { useProjectListStore } from '@renderer/stores/useProjectListStore'

// 类型别名
type Project = components['schemas']['ProjectRead']

const projectListStore = useProjectListStore()
const { projects, isLoading } = storeToRefs(projectListStore)

const createDialogRef = ref<InstanceType<typeof ProjectCreateDialog>>()
const emit = defineEmits(['project-selected'])

// 搜索与排序（仅前端，不改接口）
const searchQuery = ref('')
// 说明：后端 Project 未提供 created_at 字段，这里用 id 自增作为“创建时间”的近似排序
type SortKey = 'created-desc' | 'created-asc' | 'name-asc' | 'name-desc'
const sortKey = ref<SortKey>('created-desc')

const displayProjects = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  let data = projects.value.slice()
  if (q) {
    data = data.filter(p => (p.name || '').toLowerCase().includes(q) || (p.description || '').toLowerCase().includes(q))
  }
  if (sortKey.value === 'created-desc') data.sort((a, b) => b.id - a.id)
  if (sortKey.value === 'created-asc') data.sort((a, b) => a.id - b.id)
  if (sortKey.value === 'name-asc') data.sort((a, b) => a.name.localeCompare(b.name))
  if (sortKey.value === 'name-desc') data.sort((a, b) => b.name.localeCompare(a.name))
  return data
})

function handleOpenCreateDialog() {
  createDialogRef.value?.open()
}

async function handleProjectCreate(projectData: any) {
  try {
    await projectListStore.createProject(projectData)
  } catch (error) {
    // 错误已在store中处理
  }
}

function handleProjectEdit(project: Project) {
  createDialogRef.value?.open(project)
}

async function handleProjectUpdate(projectId: number, projectData: any) {
  try {
    await projectListStore.updateProject(projectId, projectData)
  } catch (error) {
    // 错误已在store中处理
  }
}

async function handleProjectDelete(project: Project) {
  try {
    await ElMessageBox.confirm(
      `确定要删除项目 "${project.name}" 吗？此操作将永久删除该项目及其所有内容，且无法恢复。`,
      '警告',
      {
        confirmButtonText: '确定删除',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
    await projectListStore.deleteProject(project.id)
  } catch (error) {
    if (error !== 'cancel') {
      // 错误已在store中处理
    }
  }
}

function handleProjectSelect(project: Project) {
  emit('project-selected', project)
}

onMounted(() => {
  projectListStore.fetchProjects()
})

// 计算首字母（中文则取首字符），用于封面徽标
function getInitial(name: string) {
  if (!name) return 'N'
  const ch = name.trim().charAt(0)
  return ch.toUpperCase()
}

// 按名称哈希映射到固定的渐变色组，保证同名项目视觉一致
function getCoverClass(name: string) {
  const palettes = ['g1','g2','g3','g4','g5','g6']
  let hash = 0
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) >>> 0
  return 'cover-' + palettes[hash % palettes.length]
}
</script>

<style scoped>
.dashboard-container {
  padding: 20px;
  /* 让容器占满父级主区，而不是视口高度，避免与顶部 Header 高度叠加产生滚动条 */
  min-height: 100%;
  box-sizing: border-box;
  overflow-y: auto;
}

/* 顶部横幅：轻渐变背景 + 适度留白，让界面更有仪式感 */
.dashboard-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 20px;
  /* 渐变更柔和，保证标题文字可读性 */
  background: linear-gradient(135deg, var(--el-color-primary-light-8), var(--el-fill-color-light) 65%);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  margin-bottom: 14px;
}
.hero-text h1 { margin: 0; font-size: 22px; color: var(--el-text-color-primary); text-shadow: 0 1px 0 rgba(255,255,255,.4); }
.subtitle { margin: 4px 0 0; color: var(--el-text-color-secondary); font-size: 13px; text-shadow: 0 1px 0 rgba(255,255,255,.35); }
.hero-cta { white-space: nowrap; }

/* 工具条：响应式换行 */
.toolbar {
  display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-bottom: 16px;
}
.search-input { width: 320px; max-width: 60vw; }
/* 排序选择器加宽，避免中文标签被截断 */
.sort-select { width: 240px; max-width: 50vw; }

/* 主体区高度无需强行撑满视口，由父级滚动控制 */
.dashboard-main { min-height: auto; }

/* 卡片：封面 + 内容区 + 悬浮操作 */
.project-card { margin-bottom: 20px; cursor: pointer; transition: transform .18s ease, box-shadow .18s ease; overflow: hidden; }
.project-card:hover { transform: translateY(-3px); }

.card-cover { height: 120px; display: flex; align-items: center; justify-content: center; color: #fff; font-weight: 700; font-size: 28px; letter-spacing: 1px; }
.cover-initial { text-shadow: 0 1px 2px rgba(0,0,0,.25); }

/* 六组固定渐变，视觉清爽且区分度高 */
.cover-g1 { background: linear-gradient(135deg, #8E9EAB, #EEF2F3); color: #2c3e50; }
.cover-g2 { background: linear-gradient(135deg, #74ebd5, #ACB6E5); }
.cover-g3 { background: linear-gradient(135deg, #f6d365, #fda085); }
.cover-g4 { background: linear-gradient(135deg, #a18cd1, #fbc2eb); }
.cover-g5 { background: linear-gradient(135deg, #84fab0, #8fd3f4); }
.cover-g6 { background: linear-gradient(135deg, #f5576c, #f093fb); }

.card-content { padding: 10px 12px 12px; position: relative; }
.title-row { display: flex; align-items: center; gap: 8px; }
.title { margin: 0; font-size: 16px; font-weight: 600; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.desc { margin: 6px 0 0; color: var(--el-text-color-regular); line-height: 1.5; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; min-height: 42px; }

/* 悬浮操作：默认透明，悬浮时显现 */
.card-actions { display: flex; gap: 6px; opacity: 0; transition: opacity .18s ease; }
.project-card:hover .card-actions { opacity: 1; }

@media (max-width: 768px) {
  .search-input { width: 100%; max-width: 100%; }
  .sort-select { width: 100%; max-width: 100%; }
}
</style> 