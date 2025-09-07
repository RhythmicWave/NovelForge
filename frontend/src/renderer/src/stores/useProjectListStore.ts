import { defineStore } from 'pinia'
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@renderer/api/request'
import type { components } from '@renderer/types/generated'

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
      projects.value = await request.get<Project[]>('/projects')
    } catch (error) {
      console.error('获取项目列表失败:', error)
      ElMessage.error('获取项目列表失败')
      throw error
    } finally {
      isLoading.value = false
    }
  }

  async function createProject(projectData: any) {
    try {
      const newProject = await request.post<Project>('/projects', projectData)
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
      await request.put(`/projects/${projectId}`, projectData)
      ElMessage.success('项目更新成功！')
      await fetchProjects()
    } catch (error) {
      ElMessage.error(`更新项目失败: ${error}`)
      throw error
    }
  }

  async function deleteProject(projectId: number) {
    try {
      await request.delete(`/projects/${projectId}`)
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