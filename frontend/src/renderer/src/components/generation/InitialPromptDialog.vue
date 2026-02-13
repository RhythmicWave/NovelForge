<template>
  <el-dialog
    v-model="dialogVisible"
    title="开始生成卡片"
    width="500px"
    :close-on-click-modal="false"
  >
    <div class="dialog-content">
      <p class="hint-text">
        你可以提供一些生成偏好或要求（可选）
      </p>
      <p class="hint-subtext">
        直接点击"开始生成"，AI 会自主决定生成内容
      </p>

      <el-checkbox v-model="useExistingContent" class="content-option">
        基于现有内容继续生成（如果卡片已有部分内容）
      </el-checkbox>

      <el-input
        v-model="userPrompt"
        type="textarea"
        :rows="4"
        placeholder="例如：年轻武者，擅长剑术，性格沉稳..."
        maxlength="500"
        show-word-limit
        @keyup.ctrl.enter="handleStartGenerate"
      />

      <div class="example-hints">
        <span class="example-label">示例：</span>
        <el-tag
          v-for="example in examples"
          :key="example"
          size="small"
          class="example-tag"
          @click="userPrompt = example"
        >
          {{ example }}
        </el-tag>
      </div>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="handleCancel">
          取消
        </el-button>
        <el-button @click="handleSkip">
          跳过，直接生成
        </el-button>
        <el-button
          type="primary"
          :disabled="!userPrompt.trim()"
          @click="handleStartGenerate"
        >
          开始生成
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

// ==================== Props & Emits ====================

const props = defineProps<{
  visible: boolean
  cardTypeName?: string
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
  confirm: [userPrompt: string, useExistingContent: boolean]
  cancel: []
}>()

// ==================== 状态管理 ====================

const dialogVisible = ref(false)
const userPrompt = ref('')
const useExistingContent = ref(false)

// 示例提示（根据卡片类型动态调整）
const examples = ref<string[]>([
  '年轻武者，擅长剑术',
  '神秘的魔法师，精通元素魔法',
  '经验丰富的商人，善于谈判'
])

// ==================== 方法 ====================

/**
 * 处理开始生成
 */
function handleStartGenerate() {
  emit('confirm', userPrompt.value.trim(), useExistingContent.value)
  dialogVisible.value = false
  userPrompt.value = ''
  useExistingContent.value = false
}

/**
 * 处理跳过
 */
function handleSkip() {
  emit('confirm', '', useExistingContent.value)
  dialogVisible.value = false
  userPrompt.value = ''
  useExistingContent.value = false
}

/**
 * 处理取消
 */
function handleCancel() {
  emit('cancel')
  dialogVisible.value = false
  userPrompt.value = ''
}

// ==================== 监听 ====================

watch(() => props.visible, (val) => {
  dialogVisible.value = val
})

watch(dialogVisible, (val) => {
  emit('update:visible', val)
})

// 根据卡片类型调整示例
watch(() => props.cardTypeName, (typeName) => {
  if (!typeName) return

  // 可以根据不同的卡片类型提供不同的示例
  if (typeName.includes('角色') || typeName.includes('Character')) {
    examples.value = [
      '年轻武者，擅长剑术',
      '神秘的魔法师，精通元素魔法',
      '经验丰富的商人，善于谈判'
    ]
  } else if (typeName.includes('章节') || typeName.includes('Chapter')) {
    examples.value = [
      '紧张刺激的战斗场景',
      '温馨的日常对话',
      '关键的剧情转折'
    ]
  } else if (typeName.includes('大纲') || typeName.includes('Outline')) {
    examples.value = [
      '三幕式结构',
      '英雄之旅模式',
      '多线叙事'
    ]
  } else {
    examples.value = [
      '简洁明了',
      '详细完整',
      '富有创意'
    ]
  }
})
</script>

<style scoped>
.dialog-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.hint-text {
  margin: 0;
  font-size: 14px;
  color: var(--el-text-color-primary);
}

.hint-subtext {
  margin: -8px 0 0 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.example-hints {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.example-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.example-tag {
  cursor: pointer;
  transition: all 0.2s;
}

.example-tag:hover {
  transform: translateY(-2px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
