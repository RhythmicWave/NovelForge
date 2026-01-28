<template>
  <div class="schema-field">
    <!-- 1. Enums (Select) -->
    <div v-if="resolvedSchema.enum" class="field-enum">
      <el-select 
        :model-value="modelValue"
        @change="handleChange"
        :placeholder="schema.title || schema.description"
        size="small"
        style="width: 100%"
        clearable
      >
        <el-option
          v-for="opt in resolvedSchema.enum"
          :key="opt"
          :label="opt"
          :value="opt"
        />
      </el-select>
    </div>

    <!-- 2. Array -->
    <div v-else-if="resolvedSchema.type === 'array'" class="field-array">
      <div class="array-header">
        <span class="array-title">{{ schema.title || '列表' }}</span>
        <el-button link type="primary" size="small" @click="addItem">
          <el-icon><Plus /></el-icon> 添加
        </el-button>
      </div>
      
      <div v-if="(!modelValue || modelValue.length === 0)" class="array-empty">
        暂无项目
      </div>
      
      <div v-else class="array-list">
        <div v-for="(item, idx) in modelValue" :key="idx" class="array-item">
          <div class="item-header">
            <span>#{{ Number(idx) + 1 }}</span>
            <el-button link type="danger" size="small" @click="removeItem(Number(idx))">
              <el-icon><Delete /></el-icon>
            </el-button>
          </div>
          <div class="item-content">
            <SchemaField
              :model-value="item"
              @update:model-value="(val) => updateItem(Number(idx), val)"
              :schema="resolvedSchema.items"
              :root-schema="rootSchema"
            />
          </div>
        </div>
      </div>
    </div>

    <!-- 3. Object -->
    <div v-else-if="resolvedSchema.type === 'object' || (resolvedSchema.properties && !resolvedSchema.type)" class="field-object">
        <!-- Object properties container -->
        <div v-if="schema.title" class="object-title">{{ schema.title }}</div>
        
        <div class="object-properties">
            <div v-for="(subSchema, key) in (resolvedSchema.properties || {})" :key="key" class="object-property">
               <div class="prop-label">
                   <span>{{ subSchema.title || key }}</span>
                   <el-tooltip v-if="subSchema.description" :content="subSchema.description" placement="top">
                       <el-icon><InfoFilled /></el-icon>
                   </el-tooltip>
               </div>
               <SchemaField
                 :model-value="modelValue ? modelValue[key] : undefined"
                 @update:model-value="(val) => updateObjectProperty(String(key), val)"
                 :schema="subSchema"
                 :root-schema="rootSchema"
               />
            </div>
        </div>
    </div>

    <!-- 4. Boolean -->
    <div v-else-if="resolvedSchema.type === 'boolean'" class="field-boolean">
      <el-switch
        :model-value="modelValue"
        @change="handleChange"
      />
    </div>

    <!-- 5. Number/Integer -->
    <div v-else-if="resolvedSchema.type === 'number' || resolvedSchema.type === 'integer'" class="field-number">
      <el-input-number
        :model-value="modelValue"
        @input="handleChange"
        size="small"
        style="width: 100%"
        :placeholder="schema.title"
      />
    </div>

    <!-- 6. String (Default) -->
    <div v-else class="field-string">
      <el-input
        :model-value="modelValue"
        @input="handleChange"
        size="small"
        :type="resolvedSchema.description?.includes('text') ? 'textarea' : 'text'"
        :placeholder="resolvedSchema.description || resolvedSchema.title"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Plus, Delete, InfoFilled } from '@element-plus/icons-vue'

const props = defineProps<{
  modelValue: any
  schema: any
  rootSchema: any
}>()

const emit = defineEmits<{
  'update:model-value': [value: any]
}>()

// 辅助函数：解析 $ref
const resolveRef = (ref: string, root: any) => {
    if (!ref || !ref.startsWith('#/')) return null;
    // 例如 #/$defs/FilterConfig
    const parts = ref.split('/').slice(1);
    let current = root;
    for (const part of parts) {
        if (current && current[part]) {
            current = current[part];
        } else {
            return null;
        }
    }
    return current;
}

const resolvedSchema = computed(() => {
    if (props.schema.$ref) {
        const resolved = resolveRef(props.schema.$ref, props.rootSchema);
        return resolved ? { ...resolved, ...props.schema } : props.schema; // 合并以保留 title 覆盖
    }
    // 处理 allOf (Pydantic 常用于 Enums/Refs)
    if (props.schema.allOf && props.schema.allOf.length > 0) {
        // 简单合并策略：取第一个有 type 或 $ref 的
        // Pydantic Enums: { allOf: [{ $ref: ... }] }
        const first = props.schema.allOf[0];
        if (first.$ref) {
           const resolved = resolveRef(first.$ref, props.rootSchema);
           return resolved ? { ...resolved, ...props.schema } : props.schema;
        }
        return { ...first, ...props.schema };
    }
    
    // 处理 anyOf (nullable 常使用 anyOf: [{type: null}, {$ref...}])
    if (props.schema.anyOf) {
        // 找到非空 schema
        const valid = props.schema.anyOf.find((s: any) => s.type !== 'null');
        if (valid) {
             if (valid.$ref) {
                 const resolved = resolveRef(valid.$ref, props.rootSchema);
                 return resolved ? { ...resolved, ...props.schema } : props.schema;
             }
             return { ...valid, ...props.schema };
        }
    }
    
    return props.schema;
})

const handleChange = (val: any) => {
  emit('update:model-value', val)
}

// 数组操作方法
const addItem = () => {
    const current = Array.isArray(props.modelValue) ? [...props.modelValue] : [];
    // 根据 items schema 确定默认值
    let defaultVal: any = null;
    const itemsSchema = resolvedSchema.value.items;
    if (itemsSchema) {
         if (itemsSchema.type === 'object' || itemsSchema.$ref) defaultVal = {};
         else if (itemsSchema.type === 'string') defaultVal = '';
         else if (itemsSchema.type === 'boolean') defaultVal = false;
    }
    
    current.push(defaultVal);
    emit('update:model-value', current);
}

const removeItem = (idx: number) => {
    if (!Array.isArray(props.modelValue)) return;
    const current = [...props.modelValue];
    current.splice(idx, 1);
    emit('update:model-value', current);
}

const updateItem = (idx: number, val: any) => {
    const current = [...(props.modelValue || [])];
    current[idx] = val;
    emit('update:model-value', current);
}

// 对象操作方法
const updateObjectProperty = (key: string, val: any) => {
    const current = { ...(props.modelValue || {}) };
    current[key] = val;
    emit('update:model-value', current);
}
</script>

<style scoped lang="scss">
.schema-field {
  width: 100%;
}

.field-array {
    border: 1px dashed var(--border-color);
    padding: 8px;
    border-radius: 4px;
    
    .array-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 8px;
        
        .array-title {
            font-size: 12px;
            font-weight: 600;
            color: var(--text-secondary);
        }
    }
    
    .array-item {
        background: #fafafa;
        border: 1px solid #ebeef5;
        border-radius: 4px;
        padding: 8px;
        margin-bottom: 8px;
        
        .item-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 4px;
            font-size: 11px;
            color: var(--text-muted);
        }
    }
}

.field-object {
    .object-title {
        font-size: 12px;
        font-weight: bold;
        margin-bottom: 8px;
        color: var(--text-primary);
        border-left: 3px solid var(--primary-color);
        padding-left: 6px;
    }
    
    .object-properties {
        display: flex;
        flex-direction: column;
        gap: 12px;
    }
    
    .object-property {
        .prop-label {
            display: flex;
            align-items: center;
            gap: 4px;
            margin-bottom: 4px;
            font-size: 12px;
            color: var(--text-secondary);
        }
    }
}
</style>
