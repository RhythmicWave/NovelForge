from typing import List, Optional
from sqlmodel import Session, select
from sqlalchemy.orm import joinedload
from fastapi import HTTPException

from app.db.models import Card, CardType, Project
from app.schemas.card import CardCreate, CardUpdate, CardTypeCreate, CardTypeUpdate
import logging
# 新增：引入动态信息模型
from app.schemas.entity import UpdateDynamicInfo, DynamicInfoType, CharacterCard, DynamicInfoItem

logger = logging.getLogger(__name__)

# 每类动态信息的建议上限（超过则保留更重要/较新者）。可按需调整。
MAX_ITEMS_BY_TYPE: dict[DynamicInfoType, int] = {
    DynamicInfoType.MENTAL_STATE: 3,
    DynamicInfoType.LEVEL: 4,
    DynamicInfoType.SKILL: 6,
    DynamicInfoType.EQUIPMENT: 4,
    DynamicInfoType.KNOWLEDGE: 4,
    DynamicInfoType.ASSET: 4,
    DynamicInfoType.BLOODLINE: 4,
    DynamicInfoType.CONNECTION: 5,
}

def _next_item_id(items: List[DynamicInfoItem]) -> int:
    try:
        return (max([it.id for it in items if isinstance(it.id, int) and it.id >= 1] or [0]) + 1)
    except Exception:
        return 1

# 默认映射：卡片类型名称 -> AI参数卡“键”（允许为名称或ID）。
# 前端 store 的 findByKey 会同时按 id 与 name 查找，因此这里写名称即可。
DEFAULT_PARAM_CARD_KEY_BY_TYPE = {
    "金手指": "金手指生成",
    "一句话梗概": "一句话梗概生成",
    "故事大纲": "大纲扩写生成",
    "世界观设定": "世界观生成",
    "核心蓝图": "蓝图生成",
    "分卷大纲": "分卷大纲生成",
    "章节大纲": "章节大纲生成",
}

class CardService:
    def __init__(self, db: Session):
        self.db = db

    def get_all_for_project(self, project_id: int) -> List[Card]:
        # Fetch all cards for the project. The tree structure will be built on the client-side.
        statement = (
            select(Card)
            .where(Card.project_id == project_id)
            .order_by(Card.display_order)
        )
        cards = self.db.exec(statement).all()
        return cards

    def get_by_id(self, card_id: int) -> Optional[Card]:
        return self.db.get(Card, card_id)

    def create(self, card_create: CardCreate, project_id: int) -> Card:
        # FEATURE: Check for singleton card type constraint
        card_type = self.db.get(CardType, card_create.card_type_id)
        if not card_type:
             raise HTTPException(status_code=404, detail=f"CardType with id {card_create.card_type_id} not found")

        if card_type.is_singleton:
            statement = select(Card).where(Card.project_id == project_id, Card.card_type_id == card_create.card_type_id)
            existing_card = self.db.exec(statement).first()
            if existing_card:
                raise HTTPException(
                    status_code=409, # Conflict
                    detail=f"A card of type '{card_type.name}' already exists in this project, and it is a singleton."
                )

        # Determine display order
        statement = select(Card).where(Card.project_id == project_id, Card.parent_id == card_create.parent_id)
        sibling_cards = self.db.exec(statement).all()
        display_order = len(sibling_cards)

        # 如果没有显式提供 ai_context_template，则从卡片类型继承默认模板
        ai_context_template = getattr(card_create, 'ai_context_template', None)
        if not ai_context_template:
            ai_context_template = card_type.default_ai_context_template

        # 若未显式指定参数卡键，则根据卡片类型名选择系统预设
        selected_ai_param_card_id = getattr(card_create, 'selected_ai_param_card_id', None)
        if not selected_ai_param_card_id:
            selected_ai_param_card_id = DEFAULT_PARAM_CARD_KEY_BY_TYPE.get(card_type.name)

        card = Card(
            **card_create.model_dump(),
            project_id=project_id,
            display_order=display_order,
            ai_context_template=ai_context_template,
            selected_ai_param_card_id=selected_ai_param_card_id,
        )
        self.db.add(card)
        self.db.commit()
        self.db.refresh(card)
        return card

    @staticmethod
    def create_initial_cards_for_project(db: Session, project_id: int):
        """
        Creates the initial set of cards for a new project, all as top-level cards (no parents).
        Also sets up the AI context injection templates.
        """
        initial_cards_setup = {
            "作品标签": {"order": 0},
            "金手指": {"order": 1},
            "一句话梗概": {"order": 2},
            "故事大纲": {"order": 3},
            "世界观设定": {"order": 4},
            "核心蓝图": {"order": 5},
        }

        for card_type_name, setup in initial_cards_setup.items():
            try:
                statement = select(CardType).where(CardType.name == card_type_name)
                card_type = db.exec(statement).first()

                if not card_type:
                    logger.warning(f"Card type '{card_type_name}' not found. Skipping initial card creation.")
                    continue

                # 通过服务创建，以便继承卡片类型的默认上下文模板与默认参数卡键
                service = CardService(db)
                new_card = service.create(CardCreate(
                    title=card_type.name,
                    card_type_id=card_type.id,
                    parent_id=None,
                    content={}
                ), project_id)
                # 更新排序（保持原有显示顺序）
                new_card.display_order = setup["order"]
                db.add(new_card)
                db.commit()
                db.refresh(new_card)
                logger.info(f"Successfully created initial card '{new_card.title}' for project {project_id}.")
            except Exception as e:
                logger.error(f"Failed to create initial card for type '{card_type_name}' in project {project_id}.", exc_info=True)
                db.rollback()

        return db.exec(select(Card).where(Card.project_id == project_id)).all()


    def update(self, card_id: int, card_update: CardUpdate) -> Optional[Card]:
        card = self.get_by_id(card_id)
        if not card:
            return None
            
        update_data = card_update.model_dump(exclude_unset=True)

        # If parent_id changes, we need to update display_order
        if 'parent_id' in update_data and card.parent_id != update_data['parent_id']:
            # This logic can be complex. For now, let's just append to the end of the new list.
            statement = select(Card).where(Card.project_id == card.project_id, Card.parent_id == update_data['parent_id'])
            sibling_cards = self.db.exec(statement).all()
            update_data['display_order'] = len(sibling_cards)
            # You might want to shift other cards' orders here as well.

        for key, value in update_data.items():
            setattr(card, key, value)
            
        self.db.add(card)
        self.db.commit()
        self.db.refresh(card)
        return card

    def delete(self, card_id: int) -> bool:
        # The recursive delete is handled by the cascade option in the relationship
        card = self.get_by_id(card_id)
        if not card:
            return False
        self.db.delete(card)
        self.db.commit()
        return True 

    def update_character_dynamic_info(self, project_id: int, update_data: UpdateDynamicInfo, queue_size: int = 5) -> List[Card]:
        """
        批量更新多个角色卡的动态信息，并应用上限与权重淘汰：
        - 新增条目：若 id==-1 则按类别分配自增 id（不重排已有 id）。
        - 合并后按权重降序保留；若权重相同按较新优先。
        - 每类上限优先使用 MAX_ITEMS_BY_TYPE，未配置则使用 queue_size。
        - 支持 modify_info_list 对已有条目权重进行修正。
        """
        updated_cards: List[Card] = []
        character_card_type_name = "角色卡"

        # 1. 获取"角色卡"的CardType ID
        card_type_stmt = select(CardType).where(CardType.name == character_card_type_name)
        character_card_type = self.db.exec(card_type_stmt).first()
        if not character_card_type:
            raise HTTPException(status_code=404, detail=f"CardType '{character_card_type_name}' not found.")

        # 2. 遍历待更新的信息列表
        for info_update in update_data.info_list:
            char_name = info_update.name

            # 3. 根据名称和类型查找对应的角色卡
            card_stmt = select(Card).where(
                Card.project_id == project_id,
                Card.title == char_name,
                Card.card_type_id == character_card_type.id
            )
            target_card = self.db.exec(card_stmt).first()

            if not target_card:
                logger.warning(f"在项目中 {project_id} 未找到名为 '{char_name}' 的角色卡，跳过更新。")
                continue

            try:
                card_content = target_card.content or {}
                # 兼容旧数据，避免模型验证报错
                card_content = _normalize_character_card_content(card_content, fallback_name=target_card.title)
                char_model = CharacterCard.model_validate(card_content)
                existing_di = char_model.dynamic_info or {}

                # 合并新增
                for info_type, new_items in (info_update.dynamic_info or {}).items():
                    if not isinstance(new_items, list):
                        continue
                    current_items: List[DynamicInfoItem] = list(existing_di.get(info_type, []) or [])
                    next_id = _next_item_id(current_items)

                    # 去重依据：info 文本
                    seen_info = { (it.info or '').strip(): it for it in current_items }
                    appended: List[DynamicInfoItem] = []
                    for it in new_items:
                        try:
                            info_text = (getattr(it, 'info', None) or '').strip()
                            weight_val = float(getattr(it, 'weight', 0.0) or 0.0)
                        except Exception:
                            info_text = ''
                            weight_val = 0.0
                        if not info_text:
                            continue
                        if info_text in seen_info:
                            # 若已存在且新权重大，则更新权重为较大者
                            exist = seen_info[info_text]
                            if weight_val > (exist.weight or 0.0):
                                exist.weight = weight_val
                            continue
                        # 分配 id（若未指定或为-1）
                        item_id = getattr(it, 'id', -1)
                        if not isinstance(item_id, int) or item_id < 1:
                            item_id = next_id
                            next_id += 1
                        appended_item = DynamicInfoItem(id=item_id, info=info_text, weight=weight_val)
                        current_items.append(appended_item)
                        appended.append(appended_item)
                        seen_info[info_text] = appended_item

                    # 应用上限：按权重降序、同权重按出现顺序保留
                    per_limit = MAX_ITEMS_BY_TYPE.get(info_type, queue_size)
                    if per_limit and len(current_items) > per_limit:
                        # 稳定排序：先按加入顺序标序（通过 id 近似代表先后），再按权重排序
                        current_items.sort(key=lambda x: (-(x.weight or 0.0), x.id))
                        current_items = current_items[:per_limit]
                        # 仍按 id 升序存储，便于阅读
                        current_items.sort(key=lambda x: x.id)

                    existing_di[info_type] = current_items

                # 应用 modify_info_list 权重修正
                if getattr(update_data, 'modify_info_list', None):
                    for mod in (update_data.modify_info_list or []):
                        if not mod or str(getattr(mod, 'name', '')) != char_name:
                            continue
                        t = getattr(mod, 'dynamic_type', None)
                        lst = existing_di.get(t)
                        if not lst:
                            continue
                        for it in lst:
                            if it.id == getattr(mod, 'id', None):
                                try:
                                    w = float(getattr(mod, 'weight', it.weight))
                                except Exception:
                                    w = it.weight
                                it.weight = max(0.0, min(1.0, w))
                                break

                # 写回
                char_model.dynamic_info = existing_di
                target_card.content = char_model.model_dump(by_alias=True, exclude_unset=True)
                self.db.add(target_card)
                updated_cards.append(target_card)

            except Exception as e:
                logger.error(f"更新角色卡 '{char_name}' (ID: {target_card.id}) 的动态信息时出错: {e}", exc_info=True)
                self.db.rollback()
                continue

        if updated_cards:
            self.db.commit()
            for card in updated_cards:
                self.db.refresh(card)

        return updated_cards

class CardTypeService:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self) -> List[CardType]:
        return self.db.exec(select(CardType)).all()

    def get_by_id(self, card_type_id: int) -> Optional[CardType]:
        return self.db.get(CardType, card_type_id)
        
    def create(self, card_type_create: CardTypeCreate) -> CardType:
        card_type = CardType.model_validate(card_type_create)
        self.db.add(card_type)
        self.db.commit()
        self.db.refresh(card_type)
        return card_type

    def update(self, card_type_id: int, card_type_update: CardTypeUpdate) -> Optional[CardType]:
        card_type = self.get_by_id(card_type_id)
        if not card_type:
            return None
        update_data = card_type_update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(card_type, key, value)
        self.db.add(card_type)
        self.db.commit()
        self.db.refresh(card_type)
        return card_type

    def delete(self, card_type_id: int) -> bool:
        card_type = self.get_by_id(card_type_id)
        if not card_type:
            return False
        # Consider cascading deletes or checks for associated cards
        self.db.delete(card_type)
        self.db.commit()
        return True 