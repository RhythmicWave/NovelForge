from typing import List, Optional
from sqlmodel import Session, select
from sqlalchemy.orm import joinedload
from fastapi import HTTPException

from app.db.models import Card, CardType, Project
from app.schemas.card import CardCreate, CardUpdate, CardTypeCreate, CardTypeUpdate
import logging
# 引入动态信息模型
from app.schemas.entity import UpdateDynamicInfo, CharacterCard, DynamicInfoItem
from sqlalchemy import update as sa_update

logger = logging.getLogger(__name__)

# 每类动态信息的建议上限（超过则保留更重要/较新者）。可按需调整。
MAX_ITEMS_BY_TYPE: dict[str, int] = {
    "心理想法/目标快照": 3,
    "等级/修为境界": 4,
    "功法/技能": 6,
    "装备/法宝": 4,
    "知识/情报": 4,
    "资产/领地": 4,
    "血脉/体质": 4,
    # DynamicInfoType.CONNECTION: 5,
}

# 全局权重阈值（默认 0.45）
WEIGHT_THRESHOLD =0.45

def _next_item_id(items: List[DynamicInfoItem]) -> int:
    try:
        return (max([it.id for it in items if isinstance(it.id, int) and it.id >= 1] or [0]) + 1)
    except Exception:
        return 1

# 统一键名：对象/其它类型 -> 中文字符串键
# 由于 DynamicInfoType 已改为 Literal，正常情况下这里直接返回字符串
# 仍保留容错：若传入对象且具有 value 字段且为字符串，则取其 value

def _normalize_dynamic_type_key(key_obj: object) -> str:
    try:
        if isinstance(key_obj, str):
            return key_obj
        value_attr = getattr(key_obj, 'value', None)
        if isinstance(value_attr, str):
            return value_attr
    except Exception:
        pass
    return str(key_obj)

class CardService:
    def __init__(self, db: Session):
        self.db = db

    def get_all_for_project(self, project_id: int) -> List[Card]:
        # 获取该项目所有卡片，树形结构将在客户端构建。
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

        # 决定显示顺序
        statement = select(Card).where(Card.project_id == project_id, Card.parent_id == card_create.parent_id)
        sibling_cards = self.db.exec(statement).all()
        display_order = len(sibling_cards)

        # 如果没有显式提供 ai_context_template，则从卡片类型继承默认模板
        ai_context_template = getattr(card_create, 'ai_context_template', None)
        if not ai_context_template:
            ai_context_template = card_type.default_ai_context_template

        card = Card(
            **card_create.model_dump(),
            project_id=project_id,
            display_order=display_order,
            ai_context_template=ai_context_template,
        )
        self.db.add(card)
        self.db.commit()
        self.db.refresh(card)
        return card

    @staticmethod
    def create_initial_cards_for_project(db: Session, project_id: int, template_items: Optional[List[dict]] = None):
        """
        # 为新项目创建初始卡片集合。
        # 如果提供了 template_items，则使用它们；否则回退到内置的默认列表（兼容旧版）。
        # template_items: List[ { card_type_id: int, display_order: int, title_override?: str } ]
        """
        if template_items is None:
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
                    if card_type:
                        # 创建卡片
                        new_card = Card(
                            title=card_type_name,
                            content={},
                            project_id=project_id,
                        card_type_id=card_type.id,
                            display_order=setup["order"],
                            ai_context_template=card_type.default_ai_context_template,
                        )
                    db.add(new_card)
                    db.commit()
                except Exception as e:
                    logger.error(f"Failed creating initial card for type {card_type_name}: {e}")
            return

        # 使用模板条目创建
        for item in sorted(template_items, key=lambda x: x.get('display_order', 0)):
            try:
                ct = db.get(CardType, item['card_type_id'])
                if not ct:
                    continue
                title = item.get('title_override') or ct.name
                new_card = Card(
                    title=title,
                    content={},
                    project_id=project_id,
                    card_type_id=ct.id,
                    display_order=item.get('display_order', 0),
                    ai_context_template=ct.default_ai_context_template,
                )
                db.add(new_card)
                db.commit()
            except Exception as e:
                logger.error(f"Failed creating initial card by template item {item}: {e}")
        return

    def update(self, card_id: int, card_update: CardUpdate) -> Optional[Card]:
        card = self.get_by_id(card_id)
        if not card:
            return None
            
        update_data = card_update.model_dump(exclude_unset=True)

        # 如果parent_id改变了，我们需要更新display_order
        if 'parent_id' in update_data and card.parent_id != update_data['parent_id']:
            # 这个逻辑可能很复杂。现在只是将新的列表追加到末尾。
            statement = select(Card).where(Card.project_id == card.project_id, Card.parent_id == update_data['parent_id'])
            sibling_cards = self.db.exec(statement).all()
            update_data['display_order'] = len(sibling_cards)


        for key, value in update_data.items():
            setattr(card, key, value)
            
        self.db.add(card)
        self.db.commit()
        self.db.refresh(card)
        return card

    def delete(self, card_id: int) -> bool:
        # 递归删除由关系中的级联选项处理
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
                # 容错读取：只处理 dynamic_info，避免整卡模型校验失败
                existing_di = dict(card_content.get("dynamic_info") or {})

                # 合并新增
                for info_type, new_items in (info_update.dynamic_info or {}).items():
                    if not isinstance(new_items, list):
                        continue
                    # 统一将键转为字符串（中文值），与前端 schema 的 properties 对齐
                    key = _normalize_dynamic_type_key(info_type)
                    current_items_raw = list(existing_di.get(key, []) or [])
                    # 将 dict -> DynamicInfoItem（容错）
                    current_items: List[DynamicInfoItem] = []
                    for it in current_items_raw:
                        if isinstance(it, DynamicInfoItem):
                            current_items.append(it)
                        elif isinstance(it, dict):
                            try:
                                current_items.append(DynamicInfoItem(**it))
                            except Exception:
                                continue
                    next_id = _next_item_id(current_items)

                    # 去重依据：info 文本
                    seen_info = { (it.info or '').strip(): it for it in current_items }
                    for it in new_items:
                        # 支持 dict 与对象两种形式
                        if isinstance(it, dict):
                            info_text_raw = it.get('info')
                            weight_raw = it.get('weight', 0.0)
                            item_id_raw = it.get('id', -1)
                        else:
                            info_text_raw = getattr(it, 'info', None)
                            weight_raw = getattr(it, 'weight', 0.0)
                            item_id_raw = getattr(it, 'id', -1)
                        try:
                            info_text = (info_text_raw or '').strip()
                            weight_val = float(weight_raw or 0.0)
                        except Exception:
                            info_text = ''
                            weight_val = 0.0
                        if not info_text:
                            continue
                        # 权重阈值过滤
                        if weight_val < WEIGHT_THRESHOLD:
                            continue
                        if info_text in seen_info:
                            exist = seen_info[info_text]
                            if weight_val > (exist.weight or 0.0):
                                exist.weight = weight_val
                            continue
                        # 分配 id（若未指定或为-1）
                        item_id = item_id_raw if isinstance(item_id_raw, int) else -1
                        if item_id < 1:
                            item_id = next_id
                            next_id += 1
                        appended_item = DynamicInfoItem(id=item_id, info=info_text, weight=weight_val)
                        current_items.append(appended_item)
                        seen_info[info_text] = appended_item

                    # 应用上限：按权重降序、同权重按出现顺序保留
                    per_limit = MAX_ITEMS_BY_TYPE.get(_normalize_dynamic_type_key(info_type), queue_size)  # 字符串键
                    if per_limit and len(current_items) > per_limit:
                        current_items.sort(key=lambda x: (-(x.weight or 0.0), x.id))
                        current_items = current_items[:per_limit]
                        current_items.sort(key=lambda x: x.id)

                    existing_di[key] = [ci.model_dump() if hasattr(ci, 'model_dump') else ci for ci in current_items]

                # 应用 modify_info_list 权重修正
                if getattr(update_data, 'modify_info_list', None):
                    for mod in (update_data.modify_info_list or []):
                        if not mod or str(getattr(mod, 'name', '')) != char_name:
                            continue
                        t_key = _normalize_dynamic_type_key(getattr(mod, 'dynamic_type', None))
                        lst_raw = existing_di.get(t_key)
                        if not lst_raw:
                            continue
                        # 统一为对象列表
                        lst: List[DynamicInfoItem] = []
                        for it in lst_raw:
                            if isinstance(it, DynamicInfoItem):
                                lst.append(it)
                            elif isinstance(it, dict):
                                try:
                                    lst.append(DynamicInfoItem(**it))
                                except Exception:
                                    continue
                        for it in lst:
                            if it.id == getattr(mod, 'id', None):
                                try:
                                    w = float(getattr(mod, 'weight', it.weight))
                                except Exception:
                                    w = it.weight
                                it.weight = max(0.0, min(1.0, w))
                                break
                        existing_di[t_key] = [ci.model_dump() if hasattr(ci, 'model_dump') else ci for ci in lst]

                # 写回（只更新 dynamic_info 字段，其它原样保留）
                card_content["dynamic_info"] = existing_di
                target_card.content = card_content
                # 显式 UPDATE，确保 JSON 写入
                try:
                    self.db.exec(
                        sa_update(Card)
                        .where(Card.id == target_card.id)
                        .values(content=card_content)
                    )
                except Exception:
                    # 回退到 ORM 方式
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
        for key, value in card_type_update.model_dump(exclude_unset=True).items():
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