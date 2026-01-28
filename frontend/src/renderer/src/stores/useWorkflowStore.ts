import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getNodeTypes, type WorkflowNodeType } from '../api/workflows'

export const useWorkflowStore = defineStore('workflow', () => {
    // State
    const nodeTypes = ref<WorkflowNodeType[]>([])
    const isLoading = ref(false)

    // Getters
    const categories = computed(() => {
        const cats = new Set(nodeTypes.value.map(n => n.category))
        return Array.from(cats)
    })

    const getNodesByCategory = (category: string) => {
        return nodeTypes.value.filter(n => n.category === category)
    }

    const getNodeType = (type: string) => {
        return nodeTypes.value.find(n => n.type === type)
    }

    // Actions
    async function fetchNodeTypes() {
        if (isLoading.value) return

        try {
            isLoading.value = true
            const res = await getNodeTypes()
            nodeTypes.value = res.node_types
        } catch (error) {
            console.error('Failed to fetch node types:', error)
        } finally {
            isLoading.value = false
        }
    }

    // --- Card Types Support ---
    const cardTypes = ref<any[]>([])

    async function fetchCardTypes() {
        if (cardTypes.value.length > 0) return // cache
        try {
            const { getCardTypes } = await import('../api/cards')
            cardTypes.value = await getCardTypes()
        } catch (error) {
            console.error('Failed to fetch card types:', error)
        }
    }

    return {
        nodeTypes,
        isLoading,
        categories,
        cardTypes,
        getNodesByCategory,
        getNodeType,
        fetchNodeTypes,
        fetchCardTypes
    }
})
