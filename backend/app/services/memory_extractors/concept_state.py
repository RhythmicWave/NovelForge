from __future__ import annotations

from app.db.models import Card
from app.schemas.entity import ConceptCard
from app.schemas.memory import ConceptStateExtraction
from app.services.memory_extractors.memory_base import (
    StructuredCardExtractorSpec,
    StructuredCardMemoryExtractor,
    merge_optional_text,
    unique_keep_order,
)


def _merge_concept_card(existing: ConceptCard, incoming: ConceptCard) -> ConceptCard:
    return ConceptCard(
        name=incoming.name or existing.name,
        entity_type="concept",
        life_span=incoming.life_span or existing.life_span,
        category=merge_optional_text(existing.category, incoming.category) or "",
        description=merge_optional_text(existing.description, incoming.description) or "",
        rule_definition=merge_optional_text(existing.rule_definition, incoming.rule_definition) or "",
        cost=merge_optional_text(existing.cost, incoming.cost),
        counter_relations=unique_keep_order([*(existing.counter_relations or []), *(incoming.counter_relations or [])])[:10],
        mastery_hint=merge_optional_text(existing.mastery_hint, incoming.mastery_hint),
        known_by=unique_keep_order([*(existing.known_by or []), *(incoming.known_by or [])])[:20],
    )


def _load_existing_concept_card(card: Card) -> ConceptCard:
    payload = dict(card.content or {})
    if not payload.get("name"):
        payload["name"] = card.title
    return ConceptCard.model_validate(payload)


_SPEC = StructuredCardExtractorSpec(
    code="concept_state",
    name="概念掌握提取",
    prompt_name="概念掌握提取",
    card_type_name="概念卡",
    output_model=ConceptStateExtraction,
    list_field_name="concepts",
    target_participant_types=("concept",),
    related_participant_types=("character", "organization", "item"),
    target_participant_key="concept_names",
    related_participant_key="related_entities",
    reference_title="已有概念卡参考",
)


class ConceptStateExtractor(StructuredCardMemoryExtractor):
    def __init__(self):
        super().__init__(_SPEC)

    def load_existing_card(self, card: Card) -> ConceptCard:
        return _load_existing_concept_card(card)

    def merge_card(self, existing: ConceptCard, incoming: ConceptCard) -> ConceptCard:
        return _merge_concept_card(existing, incoming)

    def build_reference_lines(self, model: ConceptCard) -> list[str]:
        return [
            f"- {model.name}",
            f"  类别: {model.category or '未填写'}",
            f"  规则: {model.rule_definition or '未填写'}",
            f"  掌握提示: {model.mastery_hint or '未填写'}",
        ]
