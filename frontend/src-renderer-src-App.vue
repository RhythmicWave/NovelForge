<script setup lang="ts">
// ...
// ... script setup content is unchanged
// ...
</script>

<template>
  <el-container class="main-layout">
    <!-- Left Sidebar -->
    <!-- ... left sidebar content is unchanged ... -->

    <!-- Main Content -->
    <el-main class="main-content">
       <Settings v-if="mainView === 'settings'" />

       <div v-else-if="mainView === 'project' && selectedProject" class="editor-area">
        <div v-if="!activeEditor" class="center-prompt editor-welcome">
          <h2>欢迎来到 {{ selectedProject.name }}</h2>
          <p>请从右侧的创作清单开始，或从左侧导航树选择一项进行编辑。</p>
        </div>
        
        <SynopsisEditor
          v-else-if="activeEditor.type === 'synopsis'"
          :project="selectedProject"
          :initial-data="projectData.synopsis"
          @update:synopsis="projectData.synopsis = $event"
        />

        <TagsEditor
          v-else-if="activeEditor.type === 'tags'"
          :project="selectedProject"
          :initial-data="projectData.tags"
          @update:tags="handleTagsUpdate"
        />

        <!-- TODO: Add other editors here -->
        
        <NovelEditor
          v-else-if="activeEditor.type === 'chapter'"
          :key="activeEditor.id"
          :chapter-id="Number(activeEditor.id.replace('chap-', ''))"
        />

      </div>
      
       <div v-else-if="mainView === 'welcome'" class="center-prompt editor-welcome">
        <h2>欢迎使用 创世星环</h2>
        <p>请从左侧选择或创建一个项目开始</p>
      </div>
    </el-main>

    <!-- Right Sidebar (Guide) -->
    <!-- ... right sidebar content is unchanged ... -->
  </el-container>
</template>

<style>
/* ... styles are unchanged ... */
</style> 