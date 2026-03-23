from __future__ import annotations

from app.db.models import Card
from app.schemas.entity import ItemCard
from app.schemas.memory import ItemStateExtraction
from app.services.memory_extractors.memory_base import (
    StructuredCardExtractorSpec,
    StructuredCardMemoryExtractor,
    merge_optional_text,
    unique_keep_order,
)


def _merge_item_card(existing: ItemCard, incoming: ItemCard) -> ItemCard:
    return ItemCard(
        name=incoming.name or existing.name,
        entity_type="item",
        life_span=incoming.life_span or existing.life_span,
        category=merge_optional_text(existing.category, incoming.category) or "",
        description=merge_optional_text(existing.description, incoming.description) or "",
        owner_hint=merge_optional_text(existing.owner_hint, incoming.owner_hint),
        power_or_effect=merge_optional_text(existing.power_or_effect, incoming.power_or_effect),
        constraints=merge_optional_text(existing.constraints, incoming.constraints),
        current_state=merge_optional_text(existing.current_state, incoming.current_state),
        important_events=unique_keep_order([*(existing.important_events or []), *(incoming.important_events or [])])[:10],
    )


def _load_existing_item_card(card: Card) -> ItemCard:
    payload = dict(card.content or {})
    if not payload.get("name"):
        payload["name"] = card.title
    return ItemCard.model_validate(payload)


_SPEC = StructuredCardExtractorSpec(
    code="item_state",
    name="物品状态提取",
    prompt_name="物品状态提取",
    card_type_name="物品卡",
    output_model=ItemStateExtraction,
    list_field_name="items",
    target_participant_types=("item",),
    related_participant_types=("character", "organization"),
    target_participant_key="item_names",
    related_participant_key="owner_names",
    reference_title="已有物品卡参考",
)


class ItemStateExtractor(StructuredCardMemoryExtractor):
    def __init__(self):
        super().__init__(_SPEC)

    def load_existing_card(self, card: Card) -> ItemCard:
        return _load_existing_item_card(card)

    def merge_card(self, existing: ItemCard, incoming: ItemCard) -> ItemCard:
        return _merge_item_card(existing, incoming)

    def build_reference_lines(self, model: ItemCard) -> list[str]:
        return [
            f"- {model.name}",
            f"  类别: {model.category or '未填写'}",
            f"  当前状态: {model.current_state or '未填写'}",
            f"  作用: {model.power_or_effect or '未填写'}",
        ]
