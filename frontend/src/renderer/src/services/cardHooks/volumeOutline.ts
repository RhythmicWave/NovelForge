import { registerHook } from './index'

registerHook('分卷大纲', async (card: any, ctx: any) => {
  // 读取当前卡片内容（新结构：字段直挂在 content 顶层）
  const currentCard = ctx.cards.value.find((c: any) => c.id === card.id)
  const content: any = currentCard?.content ?? {}

  const newCharacterCards: any[] = Array.isArray(content?.new_character_cards)
    ? content.new_character_cards
    : []

  if (!newCharacterCards.length) return

  // 角色卡类型ID
  const characterTypeId = ctx.getCardTypeIdByName('角色卡')
  if (!characterTypeId) return

  // 已存在的子角色标题集合（仅限当前分卷大纲卡的子卡片，且类型为“角色卡”）
  const existingChildByTitle = new Set(
    ctx.cards.value
      .filter((c: any) => c.parent_id === card.id && c.card_type_id === characterTypeId)
      .map((c: any) => c.title)
  )

  // 为每个新角色创建子卡片
  for (const ch of newCharacterCards) {
    const title = ch?.name || '未命名角色'
    if (existingChildByTitle.has(title)) continue
    await ctx.addCard({
      title,
      parent_id: card.id,
      card_type_id: characterTypeId,
      content: ch || {}
    })
  }

  // 清空 content.new_character_cards，保持其他字段不变
  const updatedContent = {
    ...content,
    new_character_cards: []
  }

  await ctx.modifyCard(card.id, { content: updatedContent }, { skipHooks: true })
}) 