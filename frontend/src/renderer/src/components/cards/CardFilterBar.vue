<template>
  <div class="card-filter-bar">
    <div class="left">
      <el-input v-model="keyword" placeholder="搜索卡片标题..." clearable class="search-input" @clear="emitChange" @input="emitChange">
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
      <el-select v-model="selectedTypes" multiple collapse-tags placeholder="类型筛选" class="type-select" @change="emitChange">
        <el-option v-for="t in typeOptions" :key="t.value" :label="t.label" :value="t.value" />
      </el-select>
    </div>
    <div class="right">
      <el-select v-model="sortKey" class="sort-select" @change="emitChange">
        <el-option label="按最近创建" value="recent" />
        <el-option label="按标题" value="title" />
        <el-option label="按类型" value="type" />
      </el-select>
      <el-segmented v-model="density" :options="densityOptions" @change="emitChange" class="density-seg" />
      <el-segmented v-model="viewMode" :options="viewOptions" @change="emitChange" class="view-seg" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { ElInput, ElSelect, ElOption, ElSegmented, ElIcon } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import type { components } from '@renderer/types/generated'

const props = defineProps<{ cardTypes: components['schemas']['CardTypeRead'][] }>()
const emit = defineEmits<{
  (e: 'change', payload: { keyword: string; types: number[]; sortKey: 'recent'|'title'|'type'; density: '舒适'|'紧凑'; view: '卡片'|'列表' }): void
}>()

const keyword = ref('')
const selectedTypes = ref<number[]>([])
const sortKey = ref<'recent'|'title'|'type'>('recent')
const density = ref<'舒适'|'紧凑'>('舒适')
const viewMode = ref<'卡片'|'列表'>('卡片')

const densityOptions = [ '舒适', '紧凑' ]
const viewOptions = [ '卡片', '列表' ]

const typeOptions = computed(() => (props.cardTypes || []).map(t => ({ label: t.name, value: t.id! })))

function emitChange() {
  emit('change', { keyword: keyword.value, types: selectedTypes.value, sortKey: sortKey.value, density: density.value, view: viewMode.value })
}
</script>

<style scoped>
.card-filter-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 0 16px 0;
}
.left { display: flex; gap: 12px; align-items: center; flex: 1; }
.right { display: flex; gap: 12px; align-items: center; }
.search-input { max-width: 360px; width: 100%; }
.type-select { min-width: 220px; }
.sort-select { width: 140px; }
.density-seg, .view-seg { --el-segmented-padding: 2px; }
</style> 