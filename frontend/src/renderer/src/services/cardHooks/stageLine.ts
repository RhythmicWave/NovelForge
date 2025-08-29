import { registerHook } from './index'

registerHook('阶段大纲', async (card: any, ctx: any) => {
	// 当前阶段卡片与内容
	const current = ctx.cards.value.find((c: any) => c.id === card.id)
	const content: any = current?.content ?? {}

	const volumeNumber: number | undefined = Number(content?.volume_number || current?.content?.volume_number)
	const stageNumber: number | undefined = Number(content?.stage_number || current?.content?.stage_number)

	// 父级应是“分卷大纲”卡片
	const parentId = current?.parent_id ?? null
	if (!parentId) return

	// 目标类型ID
	const chapterOutlineTypeId = ctx.getCardTypeIdByName('章节大纲')
	const chapterTypeId = ctx.getCardTypeIdByName('章节正文')
	if (!chapterOutlineTypeId || !chapterTypeId) return

	// 解析 chapter_outline_list：元素形如 ChapterOutline
	const chapterOutlines: any[] = Array.isArray(content?.chapter_outline_list) ? content.chapter_outline_list : []
	if (chapterOutlines.length === 0) return

	// 工具：从各种形态提取名称（字符串或对象）
	const toName = (x: any): string => {
		if (!x) return ''
		if (typeof x === 'string') return x.trim()
		if (typeof x === 'object') return String(x.name || x.title || x.label || '').trim()
		return ''
	}
	const toNameList = (arr: any): string[] => Array.isArray(arr) ? Array.from(new Set(arr.map(toName).filter(Boolean))) : []

	// 已存在的“章节大纲/章节正文”子卡
	const existingChildren = ctx.cards.value.filter((c: any) => c.parent_id === card.id && (c.card_type_id === chapterOutlineTypeId || c.card_type_id === chapterTypeId))
	const outlinesByChapter = new Map<number, any>()
	const chaptersByChapter = new Map<number, any>()
	for (const ch of existingChildren) {
		const chNum = Number((ch?.content as any)?.chapter_number)
		if (!Number.isFinite(chNum)) continue
		if (ch.card_type_id === chapterOutlineTypeId) outlinesByChapter.set(chNum, ch)
		else if (ch.card_type_id === chapterTypeId) chaptersByChapter.set(chNum, ch)
	}

	// 逐条处理章节大纲
	for (const item of chapterOutlines) {
		const chapterNo = Number(item?.chapter_number)
		if (!Number.isFinite(chapterNo) || chapterNo <= 0) continue
		const outlineTitle: string = typeof item?.title === 'string' && item.title.trim() ? String(item.title).trim() : `第${chapterNo}章`
		const outlineEntityListRaw = (item as any)?.entity_list
		const outlineEntityNames = toNameList(outlineEntityListRaw)

		// --- 章节大纲卡 ---
		const existingOutline = outlinesByChapter.get(chapterNo)
		const outlineContent = {
			// 保持 ChapterOutline 结构：直接存回后端产出的字段，必要字段兜底
			volume_number: Number.isFinite(Number(item?.volume_number)) ? Number(item.volume_number) : (volumeNumber || 0),
			chapter_number: chapterNo,
			title: outlineTitle,
			// 保留 item 的其余字段（如 overview/entity_list 等）
			...item,
		}
		if (existingOutline) {
			const payload: any = { content: { ...(existingOutline.content || {}), ...outlineContent } }
			// 同步标题
			if (existingOutline.title !== outlineTitle) payload.title = outlineTitle
			await ctx.modifyCard(existingOutline.id, payload, { skipHooks: true })
		} else {
			await ctx.addCard({
				title: outlineTitle,
				parent_id: card.id,
				card_type_id: chapterOutlineTypeId,
				content: outlineContent,
			}, { silent: true })
		}

		// --- 章节正文卡 ---
		const existingChapter = chaptersByChapter.get(chapterNo)
		const nextChapterCore = {
			volume_number: Number.isFinite(Number(item?.volume_number)) ? Number(item.volume_number) : (volumeNumber || 0),
			stage_number: stageNumber || 1,
			chapter_number: chapterNo,
			title: outlineTitle,
			entity_list: outlineEntityNames, // 章节正文仅用纯名称
		}
		if (existingChapter) {
			const mergedContent = {
				...(existingChapter.content || {}),
				...nextChapterCore,
			}
			const payload: any = { content: mergedContent }
			if (existingChapter.title !== outlineTitle) payload.title = outlineTitle
			await ctx.modifyCard(existingChapter.id, payload, { skipHooks: true })
		} else {
			await ctx.addCard({
				title: outlineTitle,
				parent_id: card.id,
				card_type_id: chapterTypeId,
				content: { ...nextChapterCore, content: '' },
			}, { silent: true })
		}
	}

	// 清空 chapter_outline_list，避免重复注入
	try {
		const next = { ...(content || {}), chapter_outline_list: [] }
		await ctx.modifyCard(card.id, { content: next }, { skipHooks: true })
	} catch {}
}) 