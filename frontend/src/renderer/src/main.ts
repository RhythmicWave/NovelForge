import './assets/main.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import App from './App.vue'
import { useAIParamCardStore } from './stores/useAIParamCardStore'
import { useAppStore } from './stores/useAppStore'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(ElementPlus)

// 初始化主题（必须在挂载前）
const appStore = useAppStore()
appStore.initTheme()

// --- Load initial data ---
// It's crucial to do this AFTER pinia is used by the app
const aiParamCardStore = useAIParamCardStore()
aiParamCardStore.loadFromLocal()

app.mount('#app')
