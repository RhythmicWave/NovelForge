import { registerHook } from './index'

registerHook('分卷大纲', async (card: any, ctx: any) => {
  // 读取当前卡片内容（新结构：字段直挂在 content 顶层）
  const currentCard = ctx.cards.value.find((c: any) => c.id === card.id)
  const content: any = currentCard?.content ?? {}

  // 兼容旧字段：new_entity_cards（按 entity_type 拆分）
  const legacyEntities: any[] = Array.isArray(content?.new_entity_cards) ? content.new_entity_cards : []
  const legacyChars = legacyEntities.filter((e: any) => (e?.entity_type || e?.type || e?.entityType) === 'character')
  const legacyScenes = legacyEntities.filter((e: any) => (e?.entity_type || e?.type || e?.entityType) === 'scene')

  // 1) 处理新增角色/场景卡片（新字段优先，旧字段兜底）
  const newCharacterCards: any[] = (Array.isArray(content?.new_character_cards) ? content.new_character_cards : [])
    .concat(Array.isArray(legacyChars) ? legacyChars : [])
  const newSceneCards: any[] = (Array.isArray(content?.new_scene_cards) ? content.new_scene_cards : [])
    .concat(Array.isArray(legacyScenes) ? legacyScenes : [])

  console.log('newCharacterCards', newCharacterCards)
  console.log('newSceneCards', newSceneCards)
  
  if (newCharacterCards.length > 0 || newSceneCards.length > 0) {
    const characterTypeId = ctx.getCardTypeIdByName('角色卡')
    const sceneTypeId = ctx.getCardTypeIdByName('场景卡')

    // 已存在的子卡（当前分卷下，按类型与标题唯一）
    const existingChildByTitleAndType = new Set(
      ctx.cards.value
        .filter((c: any) => c.parent_id === card.id)
        .map((c: any) => `${c.card_type_id}::${c.title}`)
    )

    // 新增角色卡
    if (characterTypeId && newCharacterCards.length > 0) {
      for (const ch of newCharacterCards) {
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

    // 新增场景卡
    if (sceneTypeId && newSceneCards.length > 0) {
      for (const sc of newSceneCards) {
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
  }

  // 2) 根据 stage_count 自动创建“阶段大纲”子卡（StageLine）
  const stageCount: number = Number(content?.stage_count || 0)
  if (stageCount > 0) {
    const stageTypeId = ctx.getCardTypeIdByName('阶段大纲')
    if (stageTypeId) {
      // 统计当前已存在的阶段子卡数量（仅限“阶段大纲”类型，父为当前分卷大纲）
      const existingStageCards = ctx.cards.value.filter(
        (c: any) => c.parent_id === card.id && c.card_type_id === stageTypeId
      )

      // 需要的数量：stageCount；若已有 n 张，则仅补足剩余（不重命名/删除已有）
      const needToCreate = Math.max(0, stageCount - existingStageCards.length)

      // 从 1 开始的连续 stage_number；已存在的尽量保留其原 content.stage_number，不做回写
      // 对新建的，按当前已有数量递增设置 stage_number
      for (let i = 1; i <= needToCreate; i++) {
        const stageNumber = existingStageCards.length + i
        const title = `阶段${stageNumber}`
        await ctx.addCard({
          title,
          parent_id: card.id,
          card_type_id: stageTypeId,
          content: { stage_number: stageNumber, volume_number: content?.volume_number } as any
        })
      }
    }
  }

  // 3) 自动创建“写作指南”子卡
  const guideTypeId = ctx.getCardTypeIdByName('写作指南')
  if (guideTypeId && content?.volume_number) {
    const existingGuideCard = ctx.cards.value.find(
      (c: any) => c.parent_id === card.id && c.card_type_id === guideTypeId
    )

    if (!existingGuideCard) {
      await ctx.addCard({
        title: `第${content.volume_number}卷-写作指南`,
        parent_id: card.id,
        card_type_id: guideTypeId,
        content: { volume_number: content.volume_number } as any
      })
    }
  }

  // 注意：不再清空 new_character_cards/new_scene_cards/new_entity_cards，
  // 以便用户删除子卡后再次保存可自动再生；通过“已存在集合”避免重复创建。
}) 