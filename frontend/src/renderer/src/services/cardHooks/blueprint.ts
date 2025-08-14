import { registerHook } from './index'

registerHook('核心蓝图',
  async (card, ctx) => {
    // --- 读取蓝图内容（新结构：字段直挂在 content 顶层） ---
    const blueprintContent: any = (ctx.cards.value.find(c => c.id === card.id)?.content) ?? {}
    const volumeCount: number = Number(blueprintContent?.volume_count || 0)
    const characterCards: any[] = Array.isArray(blueprintContent?.character_cards) ? blueprintContent.character_cards : []
    const sceneCards: any[] = Array.isArray(blueprintContent?.scene_cards) ? blueprintContent.scene_cards : []

    // --- 1) 分卷卡片自动创建 ---
    if (volumeCount > 0) {
      const volumeTypeId = ctx.getCardTypeIdByName('分卷大纲')
      if (volumeTypeId) {
        const existingVolumeTitles = new Set(
          ctx.cards.value
            .filter(c => c.card_type_id === volumeTypeId)
            .map(c => c.title)
        )
        for (let i = 1; i <= volumeCount; i++) {
          const title = `第${i}卷`
          if (!existingVolumeTitles.has(title)) {
            await ctx.addCard({
              title,
              parent_id: null,
              card_type_id: volumeTypeId,
              content: { volume_number: i } as any
            })
          }
        }
      }
    }

    // --- 2) 角色/场景卡片：作为蓝图子卡片自动创建 ---
    const characterTypeId = ctx.getCardTypeIdByName('角色卡')
    const sceneTypeId = ctx.getCardTypeIdByName('场景卡')

    const existingChildByTitleAndType = new Set(
      ctx.cards.value
        .filter(c => c.parent_id === card.id)
        .map(c => `${c.card_type_id}::${c.title}`)
    )

    if (characterTypeId && characterCards.length > 0) {
      for (const ch of characterCards) {
        const title = ch?.name || '未命名角色'
        const key = `${characterTypeId}::${title}`
        if (!existingChildByTitleAndType.has(key)) {
          await ctx.addCard({
            title,
            parent_id: card.id,
            card_type_id: characterTypeId,
            content: ch || {}
          })
        }
      }
    }

    if (sceneTypeId && sceneCards.length > 0) {
      for (const sc of sceneCards) {
        const title = sc?.name || '未命名场景'
        const key = `${sceneTypeId}::${title}`
        if (!existingChildByTitleAndType.has(key)) {
          await ctx.addCard({
            title,
            parent_id: card.id,
            card_type_id: sceneTypeId,
            content: sc || {}
          })
        }
      }
    }

    // --- 3) 清空蓝图中原有列表，避免数据不同步 ---
    const clearedContent = {
      ...(ctx.cards.value.find(c => c.id === card.id)?.content || {}),
      character_cards: [],
      scene_cards: []
    }
    await ctx.modifyCard(card.id, { content: clearedContent }, { skipHooks: true })
  }
)