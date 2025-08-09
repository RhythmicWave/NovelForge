<template>
  <div class="prompt-workshop">
    <div class="toolbar">
      <h2>提示词工坊</h2>
      <el-button type="primary" @click="handleCreate">新建提示词</el-button>
    </div>
    <el-table :data="prompts" style="width: 100%" v-loading="loading">
      <el-table-column prop="name" label="名称" width="180" />
      <el-table-column prop="description" label="描述" />
      <el-table-column label="操作" width="180">
        <template #default="{ row }">
          <el-button size="small" @click="handleEdit(row)">编辑</el-button>
          <el-popconfirm title="删除该提示词？" @confirm="handleDelete(row.id)" v-if="!isBuiltInPrompt(row)">
            <template #reference>
              <el-button size="small" type="danger" :disabled="isBuiltInPrompt(row)">删除</el-button>
            </template>
          </el-popconfirm>
          <el-button v-else size="small" type="danger" plain disabled>删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="600px">
      <el-form :model="currentPrompt" label-width="80px" ref="promptForm">
        <el-form-item label="名称" prop="name" :rules="{ required: true, message: '请输入名称', trigger: 'blur' }">
          <el-input v-model="currentPrompt.name" />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input v-model="currentPrompt.description" type="textarea" />
        </el-form-item>
        <el-form-item label="模板" prop="template" :rules="{ required: true, message: '请输入模板内容', trigger: 'blur' }">
          <el-input v-model="currentPrompt.template" type="textarea" :rows="10" />
          <div class="template-hint">
            使用 <code>${variable}</code> 的形式来定义占位符，例如 <code>${text_content}</code>。
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" @click="handleSave" :loading="saving">保存</el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import type { FormInstance } from 'element-plus';
import request from '@renderer/api/request';

interface Prompt {
  id: number;
  name: string;
  description: string;
  template: string;
  built_in?: boolean;
}

const prompts = ref<Prompt[]>([]);
const loading = ref(false);
const dialogVisible = ref(false);
const saving = ref(false);
const currentPrompt = ref<Partial<Prompt>>({});
const promptForm = ref<FormInstance>();

const dialogTitle = computed(() => (currentPrompt.value.id ? '编辑提示词' : '新建提示词'));

const PRESET_PROMPT_NAMES = new Set(['polishing','standard_continuation','task0','task1','task2','task3','task4','task5','task6','task7']);
const isBuiltInPrompt = (row: Prompt) => !!row.built_in || PRESET_PROMPT_NAMES.has(row.name);

async function fetchPrompts() {
  loading.value = true;
  try {
    prompts.value = await request.get<Prompt[]>('/prompts');
  } catch (error) {
    ElMessage.error('加载提示词列表失败');
  } finally {
    loading.value = false;
  }
}

function handleCreate() {
  currentPrompt.value = { name: '', description: '', template: '' };
  dialogVisible.value = true;
}

function handleEdit(prompt: Prompt) {
  currentPrompt.value = { ...prompt };
  dialogVisible.value = true;
}

async function handleSave() {
  if (!promptForm.value) return;
  await promptForm.value.validate(async (valid) => {
    if (valid) {
      saving.value = true;
      try {
        if (currentPrompt.value.id) {
          await request.put(`/prompts/${currentPrompt.value.id}`, currentPrompt.value);
        } else {
          await request.post('/prompts', currentPrompt.value);
        }
        ElMessage.success('保存成功');
        dialogVisible.value = false;
        fetchPrompts();
      } catch (error) {
        ElMessage.error('保存失败');
      } finally {
        saving.value = false;
      }
    }
  });
}

async function handleDelete(id: number) {
  try {
    await ElMessageBox.confirm('确定要删除这个提示词吗？', '警告', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    });
    await request.delete(`/prompts/${id}`);
    ElMessage.success('删除成功');
    fetchPrompts();
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败');
    }
  }
}

onMounted(fetchPrompts);
</script>

<style scoped>
.prompt-workshop { padding: 20px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.template-hint { font-size: 12px; color: #909399; margin-top: 5px; }
</style> 