from __future__ import annotations

from app.db.models import Card
from app.schemas.entity import OrganizationCard, OrganizationCardMemory
from app.schemas.memory import OrganizationStateExtraction
from app.services.memory_extractors.memory_base import (
    StructuredCardExtractorSpec,
    StructuredCardMemoryExtractor,
    merge_optional_text,
    unique_keep_order,
)


def _merge_organization_card(existing: OrganizationCard, incoming: OrganizationCardMemory) -> OrganizationCard:
    return OrganizationCard(
        name=incoming.name or existing.name,
        entity_type="organization",
        life_span=incoming.life_span or existing.life_span,
        description=merge_optional_text(existing.description, incoming.description) or "",
        influence=merge_optional_text(existing.influence, incoming.influence),
        relationship=unique_keep_order([*(existing.relationship or []), *(incoming.relationship or [])])[:12],
        dynamic_state=unique_keep_order([*(existing.dynamic_state or []), *(incoming.dynamic_state or [])])[-8:],
        last_appearance=existing.last_appearance,
    )


def _load_existing_organization_card(card: Card) -> OrganizationCard:
    payload = dict(card.content or {})
    payload.setdefault("name", card.title)
    payload.setdefault("entity_type", "organization")
    payload.setdefault("life_span", "长期")
    payload["description"] = payload.get("description") or ""
    if payload.get("influence") == "":
        payload["influence"] = None
    if not isinstance(payload.get("relationship"), list):
        payload["relationship"] = []
    if not isinstance(payload.get("dynamic_state"), list):
        payload["dynamic_state"] = []
    return OrganizationCard.model_validate(payload)


_SPEC = StructuredCardExtractorSpec(
    code="organization_state",
    name="组织状态提取",
    prompt_name="组织状态提取",
    card_type_name="组织卡",
    output_model=OrganizationStateExtraction,
    list_field_name="organizations",
    target_participant_types=("organization",),
    related_participant_types=("character", "organization", "scene", "item", "concept"),
    target_participant_key="organization_names",
    related_participant_key="related_entities",
    reference_title="已有组织卡参考",
)


class OrganizationStateExtractor(StructuredCardMemoryExtractor):
    def __init__(self):
        super().__init__(_SPEC)

    def load_existing_card(self, card: Card) -> OrganizationCard:
        return _load_existing_organization_card(card)

    def merge_card(self, existing: OrganizationCard, incoming: OrganizationCardMemory) -> OrganizationCard:
        return _merge_organization_card(existing, incoming)

    def build_reference_lines(self, model: OrganizationCard) -> list[str]:
        return [
            f"- {model.name}",
            f"  简介: {model.description or '未填写'}",
            f"  当前影响力: {model.influence or '未填写'}",
            f"  对外关系: {'；'.join(model.relationship or []) or '暂无'}",
            f"  当前状态: {'；'.join(model.dynamic_state or []) or '暂无'}",
        ]
