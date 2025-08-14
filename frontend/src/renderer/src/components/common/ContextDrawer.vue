<template>
  <el-drawer v-model="visible" :with-header="false" size="36%" append-to-body>
    <div class="drawer-wrapper">
      <div class="drawer-header">
        <h3>上下文注入</h3>
        <el-button text @click="visible=false">关闭</el-button>
      </div>

      <div class="section">
        <h4>上下文模板</h4>
        <el-input v-model="aiContext" type="textarea" :rows="8" placeholder="在此编辑上下文模板，支持 @ 引用" class="context-area" :spellcheck="false" />
        <div class="chips">
          <el-tag v-for="(t, i) in tokens" :key="i" closable @close="removeToken(t)">@{{ t }}</el-tag>
        </div>
        <div class="actions">
          <el-button size="small" @click="$emit('open-selector', aiContext)">插入引用 @</el-button>
          <el-button size="small" type="primary" @click="apply">应用到卡片</el-button>
        </div>
      </div>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useCardStore } from '@renderer/stores/useCardStore'
import { storeToRefs } from 'pinia'
import { unwrapChapterOutline, extractParticipantsFrom } from '@renderer/services/contextHelpers'

const props = defineProps<{
  modelValue: boolean
  contextTemplate: string
  previewText?: string
}>()
const emit = defineEmits(['update:modelValue','apply-context','open-selector'])

const visible = ref(props.modelValue)
watch(() => props.modelValue, v => visible.value = v)
watch(visible, v => emit('update:modelValue', v))

const aiContext = ref(props.contextTemplate)
watch(() => props.contextTemplate, v => aiContext.value = v)

const tokenRegex = /@([^\s]+)/g
const tokens = computed(() => {
  const out: string[] = []
  const text = aiContext.value || ''
  let m: RegExpExecArray | null
  while ((m = tokenRegex.exec(text))) out.push(m[1])
  return out
})

function removeToken(token: string) {
  const full = '@' + token
  aiContext.value = (aiContext.value || '').split(full).join('')
}

function apply() { emit('apply-context', aiContext.value) }

// 在抽屉中输入 @ 时弹出选择器
const cardStore = useCardStore()
const { activeCard } = storeToRefs(cardStore)
let drawerTextarea: HTMLTextAreaElement | null = null
watch(() => visible.value, (v) => {
  if (v) {
    setTimeout(() => {
      drawerTextarea = document.querySelector('.context-area textarea') as HTMLTextAreaElement | null
      drawerTextarea?.addEventListener('input', handleDrawerInput)
    }, 0)
  } else {
    drawerTextarea?.removeEventListener('input', handleDrawerInput)
    drawerTextarea = null
  }
})

function handleDrawerInput(ev: Event) {
  const textarea = ev.target as HTMLTextAreaElement
  const cursorPos = textarea.selectionStart
  const lastChar = textarea.value.substring(cursorPos - 1, cursorPos)
  if (lastChar === '@') {
    emit('open-selector', textarea.value)
  }
}
</script>

<style scoped>
.drawer-wrapper { display: flex; flex-direction: column; gap: 16px; height: 100%; }
.drawer-header { display: flex; justify-content: space-between; align-items: center; }
.section { display: flex; flex-direction: column; gap: 8px; }
.context-area { width: 100%; }
.actions { display: flex; gap: 8px; }
.chips { display: flex; gap: 6px; flex-wrap: wrap; }
</style> 