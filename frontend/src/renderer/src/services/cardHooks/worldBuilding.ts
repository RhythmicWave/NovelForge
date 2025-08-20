import { registerHook } from './index'

// 钩子：世界观设定（WorldBuildingResponse）
// 行为：把 world_view.social_system.major_power_camps 中的组织转为子“组织卡”，然后清空该列表
registerHook('世界观设定', async (card: any, ctx: any) => {
  const current = ctx.cards.value.find((c: any) => c.id === card.id)
  const content: any = current?.content ?? {}

  const majorPowerCamps: any[] = Array.isArray(content?.world_view?.social_system?.major_power_camps)
    ? content.world_view.social_system.major_power_camps
    : []

  if (!majorPowerCamps.length) return

  const orgTypeId = ctx.getCardTypeIdByName('组织卡')
  if (!orgTypeId) return

  // 已存在的同类型子卡（按“类型+标题”键防重复）
  const existingByKey = new Set(
    ctx.cards.value
      .filter((c: any) => c.parent_id === card.id)
      .map((c: any) => `${c.card_type_id}::${c.title}`)
  )

  for (const org of majorPowerCamps) {
    const title = org?.name || '未命名组织'
    const key = `${orgTypeId}::${title}`
    if (!existingByKey.has(key)) {
      await ctx.addCard({
        title,
        parent_id: card.id,
        card_type_id: orgTypeId,
        content: org || {}
      })
    }
  }

  // 清空列表字段，保持其余不变
  const updatedContent = {
    ...content,
    world_view: {
      ...(content.world_view || {}),
      social_system: {
        ...(content.world_view?.social_system || {}),
        major_power_camps: []
      }
    }
  }

  await ctx.modifyCard(card.id, { content: updatedContent }, { skipHooks: true })
}) 