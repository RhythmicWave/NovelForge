from typing import List, Optional
from sqlmodel import Session, select
from sqlalchemy.orm import joinedload

from app.db.models import Card, CardType, Project
from app.schemas.card import CardCreate, CardUpdate, CardTypeCreate, CardTypeUpdate
from app.exceptions import BusinessException
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

# ---- ：子树工具 ----

def _fetch_children(db: Session, parent_ids: List[int]) -> List[Card]:
    if not parent_ids:
        return []
    stmt = select(Card).where(Card.parent_id.in_(parent_ids))
    return db.exec(stmt).all()


def _collect_subtree(db: Session, root: Card) -> List[Card]:
    """按广度优先收集包含 root 在内的整棵子树（返回顺序：父在前、子在后）。"""
    result: List[Card] = []
    queue: List[Card] = [root]
    while queue:
        node = queue.pop(0)
        result.append(node)
        children = _fetch_children(db, [node.id])
        queue.extend(children)
    return result


def _next_display_order(db: Session, project_id: int, parent_id: Optional[int]) -> int:
    stmt = select(Card).where(Card.project_id == project_id, Card.parent_id == parent_id)
    siblings = db.exec(stmt).all()
    return len(siblings)


def _shallow_clone(src: Card, project_id: int, parent_id: Optional[int], display_order: int) -> Card:
    return Card(
        title=src.title,
        model_name=src.model_name,
        content=dict(src.content or {}),
        parent_id=parent_id,
        card_type_id=src.card_type_id,
        json_schema=dict(src.json_schema or {}) if src.json_schema is not None else None,
        ai_params=dict(src.ai_params or {}) if src.ai_params is not None else None,
        project_id=project_id,
        display_order=display_order,
        ai_context_template=src.ai_context_template,
    )

# ---- 标题后缀生成 ----

def _generate_non_conflicting_title(db: Session, project_id: int, base_title: str) -> str:
    title = (base_title or '').strip() or '新卡片'
    # 收集同项目内所有以 base_title 开头且形如 base_title(数字) 的标题
    stmt = select(Card.title).where(Card.project_id == project_id)
    titles = db.exec(stmt).all() or []
    existing_titles = set(titles)
    if title not in existing_titles:
        return title
    # 找最大后缀
    import re
    pattern = re.compile(rf"^{re.escape(title)}\((\d+)\)$")
    max_n = 0
    for t in existing_titles:
        m = pattern.match(str(t))
        if m:
            try:
                n = int(m.group(1))
                if n > max_n:
                    max_n = n
            except Exception:
                continue
    return f"{title}({max_n + 1})"


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
             raise BusinessException(f"CardType with id {card_create.card_type_id} not found", status_code=404)

        # 单例限制：在保留项目(__free__)中放行
        proj = self.db.get(Project, project_id)
        is_free_project = getattr(proj, 'name', None) == "__free__"
        if card_type.is_singleton and not is_free_project:
            statement = select(Card).where(Card.project_id == project_id, Card.card_type_id == card_create.card_type_id)
            existing_card = self.db.exec(statement).first()
            if existing_card:
                raise BusinessException(
                    f"A card of type '{card_type.name}' already exists in this project, and it is a singleton.",
                    status_code=409
                )

        # 决定显示顺序
        statement = select(Card).where(Card.project_id == project_id, Card.parent_id == card_create.parent_id)
        sibling_cards = self.db.exec(statement).all()
        display_order = len(sibling_cards)

        # 如果没有显式提供 ai_context_template，则从卡片类型继承默认模板
        ai_context_template = getattr(card_create, 'ai_context_template', None)
        # 自由卡默认不注入上下文：强制清空模板
        if is_free_project:
            ai_context_template = None
        elif not ai_context_template:
            ai_context_template = card_type.default_ai_context_template

        # 自动处理标题冲突：相同标题追加 (n)
        final_title = _generate_non_conflicting_title(self.db, project_id, getattr(card_create, 'title', '') or card_type.name)

        card = Card(
            **{ **card_create.model_dump(), 'title': final_title },
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

    # ---- 移动与复制 ----
    def move_card(self, card_id: int, target_project_id: int, parent_id: Optional[int] = None) -> Optional[Card]:
        root = self.get_by_id(card_id)
        if not root:
            return None
        # 收集子树
        subtree = _collect_subtree(self.db, root)
        id_set = {c.id for c in subtree}
        # 校验：若指定 parent_id，不能把父节点设为子树内部其它节点（避免环）
        if parent_id and parent_id in id_set and parent_id != root.id:
            raise BusinessException("Cannot set parent to a descendant of itself", status_code=400)
        # 目标父节点项目校验
        if parent_id is not None:
            parent_card = self.get_by_id(parent_id)
            if not parent_card:
                raise BusinessException("Target parent card not found", status_code=404)
            if parent_card.project_id != target_project_id:
                raise BusinessException("Target parent card not in target project", status_code=400)
        # 非保留项目的单例限制（跨项目移动时校验）
        if target_project_id != root.project_id:
            target_proj = self.db.get(Project, target_project_id)
            is_target_free = getattr(target_proj, 'name', None) == "__free__"
            if root.card_type and getattr(root.card_type, 'is_singleton', False) and not is_target_free:
                exists_stmt = select(Card).where(Card.project_id == target_project_id, Card.card_type_id == root.card_type_id)
                exists = self.db.exec(exists_stmt).first()
                if exists:
                    raise BusinessException(f"A card of type '{root.card_type.name}' already exists in target project (singleton)", status_code=409)
        # 更新项目ID（整棵子树）
        for node in subtree:
            node.project_id = target_project_id
        # 调整根的父与显示顺序
        root.parent_id = parent_id
        # 单例限制：在保留项目(__free__)内的同类型允许多个，因此 display_order 也允许直接追加
        root.display_order = _next_display_order(self.db, target_project_id, parent_id)
        # 提交
        for node in subtree:
            self.db.add(node)
        self.db.commit()
        self.db.refresh(root)
        return root

    def copy_card(self, card_id: int, target_project_id: int, parent_id: Optional[int] = None) -> Optional[Card]:
        src_root = self.get_by_id(card_id)
        if not src_root:
            return None
        # 非保留项目的单例限制（复制到目标时校验根类型）
        target_proj = self.db.get(Project, target_project_id)
        is_target_free = getattr(target_proj, 'name', None) == "__free__"
        if src_root.card_type and getattr(src_root.card_type, 'is_singleton', False) and not is_target_free:
            exists_stmt = select(Card).where(Card.project_id == target_project_id, Card.card_type_id == src_root.card_type_id)
            exists = self.db.exec(exists_stmt).first()
            if exists:
                raise BusinessException(f"A card of type '{src_root.card_type.name}' already exists in target project (singleton)", status_code=409)
        # 收集子树，按父在前的顺序复制
        subtree = _collect_subtree(self.db, src_root)
        old_to_new_id: dict[int, int] = {}
        new_nodes_by_old_id: dict[int, Card] = {}
        for node in subtree:
            # 计算新父ID
            if node.id == src_root.id:
                new_parent_id = parent_id
                new_order = _next_display_order(self.db, target_project_id, new_parent_id)
            else:
                old_parent_id = node.parent_id
                new_parent_id = old_to_new_id.get(old_parent_id) if old_parent_id is not None else None
                new_order = _next_display_order(self.db, target_project_id, new_parent_id)
            clone = _shallow_clone(node, target_project_id, new_parent_id, new_order)
            # 复制时也避免标题冲突
            clone.title = _generate_non_conflicting_title(self.db, target_project_id, clone.title)
            self.db.add(clone)
            self.db.commit()
            self.db.refresh(clone)
            old_to_new_id[node.id] = clone.id
            new_nodes_by_old_id[node.id] = clone
        return new_nodes_by_old_id.get(src_root.id)


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