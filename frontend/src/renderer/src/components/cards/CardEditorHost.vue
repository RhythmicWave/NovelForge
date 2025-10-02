<template>
  <div class="card-editor-host">
    <component :is="activeEditorComponent" :key="card.id" :card="card" :prefetched="prefetched" />
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue';
import type { CardRead } from '@renderer/api/cards';

const props = defineProps<{
  card: CardRead;
  prefetched?: any;
}>();

// --- Editor Component Map ---
// This map allows us to resolve a string name to an actual component.
// 只有需要完全自定义外壳的编辑器才在这里注册
// 如果只是内容编辑器不同（如章节正文的 CodeMirrorEditor），
// 应该通过 GenericCardEditor 的 content_editor_component 配置
const editorMap: Record<string, any> = {
  TagsEditor: defineAsyncComponent(() => import('../editors/TagsEditor.vue')),
  // Add other custom editors here in the future
};

// --- Default Editor ---
const GenericCardEditor = defineAsyncComponent(() => import('./GenericCardEditor.vue'));


const activeEditorComponent = computed(() => {
  const customEditorName = props.card.card_type.editor_component;
  if (customEditorName && editorMap[customEditorName]) {
    return editorMap[customEditorName];
  }
  return GenericCardEditor;
});
</script>

<style scoped>
.card-editor-host {
  height: 100%;
  width: 100%;
}
</style> 