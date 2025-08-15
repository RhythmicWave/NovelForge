<template>
  <div class="knowledge-manager">
    <div class="header">
      <h4>知识库</h4>
      <el-button type="primary" size="small" @click="openEditor()">新建知识</el-button>
    </div>

    <el-table :data="items" height="60vh" size="small" v-loading="loading">
      <el-table-column prop="name" label="名称" width="90" />
      <el-table-column prop="description" label="描述" min-width="150" />
      <el-table-column label="内置" width="80">
        <template #default="{ row }">
          <el-tag size="small" :type="row.built_in ? 'info' : 'success'">{{ row.built_in ? '内置' : '自定义' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="180" align="right">
        <template #default="{ row }">
          <el-button size="small" @click="openEditor(row)">编辑</el-button>
          <el-popconfirm title="删除该知识？" @confirm="remove(row)">
            <template #reference>
              <el-button size="small" type="danger" plain :disabled="row.built_in">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- 将抽屉改为模态对话框，避免抽屉内嵌抽屉 -->
    <el-dialog v-model="editor.visible" :title="editor.editing ? '编辑知识' : '新建知识'" width="50%" append-to-body>
      <el-form label-position="top" :model="editor.form">
        <el-form-item label="名称"><el-input v-model="editor.form.name" :disabled="editor.editing && editor.form.built_in" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="editor.form.description" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="内容"><el-input v-model="editor.form.content" type="textarea" :rows="14" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editor.visible=false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listKnowledge, createKnowledge, updateKnowledge, deleteKnowledge, type Knowledge } from '@renderer/api/setting'

const loading = ref(false)
const items = ref<Knowledge[]>([])

const editor = ref<{ visible: boolean; editing: boolean; form: Partial<Knowledge> }>({ visible: false, editing: false, form: {} })

async function fetchList() {
  loading.value = true
  try {
    items.value = await listKnowledge()
  } catch (e:any) {
    ElMessage.error('加载知识库失败')
  } finally {
    loading.value = false
  }
}

function openEditor(row?: Knowledge) {
  editor.value.visible = true
  editor.value.editing = !!row
  editor.value.form = row ? { ...row } : { name: '', description: '', content: '' }
}

async function save() {
  try {
    const f = editor.value.form
    if (!f?.name || !f.content) { ElMessage.warning('请填写名称与内容'); return }
    if (editor.value.editing && f.id) {
      const saved = await updateKnowledge(f.id, { name: f.name, description: f.description || '', content: f.content })
      ElMessage.success('已更新')
      // 局部更新
      if (saved) {
        const idx = items.value.findIndex(i => i.id === saved.id)
        if (idx >= 0) items.value[idx] = saved
      }
    } else {
      const created = await createKnowledge({ name: f.name, description: f.description || '', content: f.content })
      ElMessage.success('已创建')
      if (created) items.value.unshift(created)
    }
    editor.value.visible = false
  } catch (e:any) {
    ElMessage.error('保存失败')
  }
}

async function remove(row: Knowledge) {
  try {
    await deleteKnowledge(row.id)
    ElMessage.success('已删除')
    items.value = items.value.filter(i => i.id !== row.id)
  } catch (e:any) {
    ElMessage.error(e?.message || '删除失败')
  }
}

fetchList()
</script>

<style scoped>
.knowledge-manager { display: flex; flex-direction: column; gap: 12px; height: 100%; }
.header { display: flex; justify-content: space-between; align-items: center; }
</style> 