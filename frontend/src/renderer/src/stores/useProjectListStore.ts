import { defineStore } from 'pinia'
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { components } from '@renderer/types/generated'
import { getProjects, createProject as apiCreateProject, updateProject as apiUpdateProject, deleteProject as apiDeleteProject } from '@renderer/api/projects'

type Project = components['schemas']['ProjectRead']
type ProjectCreate = components['schemas']['ProjectCreate']
type ProjectUpdate = components['schemas']['ProjectUpdate']

export const useProjectListStore = defineStore('projectList', () => {
  // 项目列表
  const projects = ref<Project[]>([])
  const isLoading = ref(false)

  // Actions
  async function fetchProjects() {
    isLoading.value = true
    try {
      const list = await getProjects()
      projects.value = (list || []).filter(p => (p.name || '') !== '__free__')
    } catch (error) {
      console.error('获取项目列表失败:', error)
      ElMessage.error('获取项目列表失败')
      throw error
    } finally {
      isLoading.value = false
    }
  }

  async function createProject(projectData: ProjectCreate) {
    try {
      const newProject = await apiCreateProject(projectData)
      await fetchProjects()
      ElMessage.success('项目创建成功！')
      return newProject
    } catch (error) {
      ElMessage.error(`创建项目失败: ${error}`)
      throw error
    }
  }

  async function updateProject(projectId: number, projectData: ProjectUpdate) {
    try {
      await apiUpdateProject(projectId, projectData)
      ElMessage.success('项目更新成功！')
      await fetchProjects()
    } catch (error) {
      ElMessage.error(`更新项目失败: ${error}`)
      throw error
    }
  }

  async function deleteProject(projectId: number) {
    try {
      // 额外前端保护：阻止删除保留项目
      const proj = projects.value.find(p => p.id === projectId)
      if (proj && (proj.name || '') === '__free__') {
        ElMessage.warning('系统保留项目不可删除')
        return
      }
      await apiDeleteProject(projectId)
      ElMessage.success('项目删除成功！')
      await fetchProjects()
    } catch (error) {
      ElMessage.error(`删除项目失败: ${error}`)
      throw error
    }
  }

  function reset() {
    projects.value = []
    isLoading.value = false
  }

  return {
    // State
    projects,
    isLoading,
    
    // Actions
    fetchProjects,
    createProject,
    updateProject,
    deleteProject,
    reset
  }
}) 