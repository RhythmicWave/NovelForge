<script setup lang="ts">
import { computed } from 'vue'
import { Handle, Position } from '@vue-flow/core'
import { NodeToolbar } from '@vue-flow/node-toolbar'

const props = defineProps<{ id: string; data: { type: string; params?: any } }>()

function summarize(type: string, params: any): string {
  const p = params || {}
  try {
    if (type === 'Card.Read') {
      const target = p.target === '$self' ? '$self' : (typeof p.target === 'object' ? (p.target?.card_id ?? p.target?.id) : p.target)
      return `Card.Read ${target != null ? `(${String(target)})` : ''}`.trim()
    }
    if (type === 'List.ForEach') {
      const listPath = p.listPath || p.list
      return `List.ForEach ${typeof listPath === 'string' ? listPath : ''}`.trim()
    }
    if (type === 'List.ForEachRange') {
      const count = p.count ?? p.countPath ?? '?'
      const start = p.start ?? 1
      return `ForEachRange count=${count} start=${start}`
    }
    if (type === 'Card.UpsertChildByTitle') {
      const ct = p.cardType || ''
      const title = p.title || p.titlePath || ''
      const source = p.useItemAsContent ? 'item' : (p.contentPath ? 'path' : (p.contentTemplate ? 'template' : ''))
      const sourceTxt = source ? ` · src:${source}` : ''
      return `UpsertChild ${ct}${title ? ` · title:${String(title).slice(0, 24)}` : ''}${sourceTxt}`
    }
    if (type === 'Card.ModifyContent') {
      const sp = p.setPath
      if (sp) return `ModifyContent ${sp}`
      const cm = p.contentMerge ? Object.keys(p.contentMerge).slice(0, 3).join(',') : ''
      return `ModifyContent ${cm}`.trim()
    }
  } catch {}
  return type
}

const title = computed(() => props.data?.type || 'Node')
const detail = computed(() => summarize(props.data?.type || '', props.data?.params))

function deleteSelf() {
  try {
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('wf-node-delete', { detail: { id: props.id } }))
    }
  } catch {}
}
</script>

<template>
  <div class="wf-node">
    <NodeToolbar :is-visible="!!($props as any)?.data?.toolbarVisible" :position="Position.Top">
      <button class="tb-btn" @click="deleteSelf">删除</button>
    </NodeToolbar>
    <Handle id="t" type="target" :position="Position.Top" />
    <Handle id="l" type="target" :position="Position.Left" />
    <div class="title">{{ title }}</div>
    <div class="detail">{{ detail }}</div>
    <Handle id="b" type="source" :position="Position.Bottom" />
    <Handle id="r" type="source" :position="Position.Right" />
  </div>
</template>

<style scoped>
.wf-node { background: var(--el-bg-color); color: var(--el-text-color-primary); border: 1px solid var(--el-border-color); border-radius: 8px; padding: 8px 10px; width: 220px; box-shadow: 0 1px 2px rgba(0,0,0,.06); }
.title { font-weight: 600; margin-bottom: 6px; }
.detail { color: var(--el-text-color-secondary); font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tb-btn { font-size: 12px; padding: 4px 8px; }
</style>


