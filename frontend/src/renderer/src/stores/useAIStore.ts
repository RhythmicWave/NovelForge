import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { generateAIContent } from '@renderer/api/ai'
import type { AIParamCard } from './useAIParamCardStore'

export const useAIStore = defineStore('ai', () => {
  // AI生成状态
  const isGenerating = ref(false)
  const currentTask = ref<string>('')
  
  // AI配置对话框状态
  const aiConfigDialog = reactive({
    visible: false,
    task: '',
    input: {} as any
  })

  // Actions
  function setGenerating(generating: boolean) {
    isGenerating.value = generating
  }

  function setCurrentTask(task: string) {
    currentTask.value = task
  }

  function showAIConfigDialog(task: string, input: any) {
    aiConfigDialog.task = task
    aiConfigDialog.input = input
    aiConfigDialog.visible = true
  }

  function hideAIConfigDialog() {
    aiConfigDialog.visible = false
  }

  async function generateContent(
    response_model_name: string,
    input_text: string, 
    llm_config_id: number,
    prompt_name?: string | null,
  ) {
    setGenerating(true)
    // Task name is now derived from the response model name for clarity in UI
    setCurrentTask(response_model_name) 
    
    try {
      const result = await generateAIContent({
        // task is no longer needed by the backend
        input: { input_text: input_text },
        llm_config_id,
        prompt_name,
        response_model_name
      } as any) // Use 'as any' to bypass strict type checking if generated types are lagging
      
      ElMessage.success('AI生成成功！')
      return result
    } catch (error) {
      ElMessage.error('AI生成失败: ' + error)
      throw error
    } finally {
      setGenerating(false)
      setCurrentTask('')
    }
  }

  function reset() {
    isGenerating.value = false
    currentTask.value = ''
    aiConfigDialog.visible = false
    aiConfigDialog.task = ''
    aiConfigDialog.input = {}
  }

  return {
    // State
    isGenerating,
    currentTask,
    aiConfigDialog,
    
    // Actions
    setGenerating,
    setCurrentTask,
    showAIConfigDialog,
    hideAIConfigDialog,
    generateContent,
    reset
  }
}) 