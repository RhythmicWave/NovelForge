from __future__ import annotations

from typing import Any, Iterable, Optional

from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import Session, select

from app.db.models import Card, CardType
from app.schemas.entity import ConceptCard
from app.schemas.memory import ConceptStateExtraction, ParticipantTyped
from app.services import prompt_service
from app.services.ai.core import llm_service
from app.services.memory_extractors.memory_base import log_extract_prompt


def _unique_keep_order(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _merge_optional_text(old: Optional[str], new: Optional[str]) -> Optional[str]:
    new_value = (new or "").strip()
    if new_value:
        return new_value
    old_value = (old or "").strip()
    return old_value or None


def _merge_concept_card(existing: ConceptCard, incoming: ConceptCard) -> ConceptCard:
    return ConceptCard(
        name=incoming.name or existing.name,
        entity_type="concept",
        life_span=incoming.life_span or existing.life_span,
        category=_merge_optional_text(existing.category, incoming.category) or "",
        description=_merge_optional_text(existing.description, incoming.description) or "",
        rule_definition=_merge_optional_text(existing.rule_definition, incoming.rule_definition) or "",
        cost=_merge_optional_text(existing.cost, incoming.cost),
        counter_relations=_unique_keep_order([*(existing.counter_relations or []), *(incoming.counter_relations or [])])[:10],
        mastery_hint=_merge_optional_text(existing.mastery_hint, incoming.mastery_hint),
        known_by=_unique_keep_order([*(existing.known_by or []), *(incoming.known_by or [])])[:20],
    )


def _load_existing_concept_card(card: Card) -> ConceptCard:
    payload = dict(card.content or {})
    if not payload.get("name"):
        payload["name"] = card.title
    return ConceptCard.model_validate(payload)


class ConceptStateExtractor:
    code = "concept_state"
    name = "概念掌握提取"
    target = "card"
    preview_supported = True
    output_model = ConceptStateExtraction
    prompt_name = "概念掌握提取"

    async def extract(
        self,
        *,
        service: Any,
        session: Session,
        project_id: int | None,
        text: str,
        participants: list[ParticipantTyped],
        llm_config_id: int,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: float | None = None,
        extra_context: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> ConceptStateExtraction:
        prompt = prompt_service.get_prompt_by_name(session, self.prompt_name)
        if not prompt:
            raise ValueError(f"未找到提示词: {self.prompt_name}")

        system_prompt = prompt.template
        schema_json = ConceptStateExtraction.model_json_schema()
        system_prompt += f"\n\n请严格按照以下 JSON Schema 输出：\n{schema_json}"

        concept_participants = [p.name for p in participants if p.type == "concept"]
        related_entities = [p.name for p in participants if p.type in {"character", "organization", "item"}]

        ref_blocks: list[str] = []
        if extra_context:
            ref_blocks.append(f"【补充上下文，仅供参考，不要机械复述】\n{extra_context}")

        if project_id and concept_participants:
            concept_card_type = session.exec(select(CardType).where(CardType.name == "概念卡")).first()
            rows = []
            if concept_card_type:
                stmt = select(Card).where(
                    Card.project_id == project_id,
                    Card.card_type_id == concept_card_type.id,
                    Card.title.in_(concept_participants),
                )
                rows = session.exec(stmt).all()
            lines: list[str] = []
            for card in rows:
                try:
                    model = _load_existing_concept_card(card)
                except Exception:
                    continue
                parts = [
                    f"- {model.name}",
                    f"  类别: {model.category or '未填写'}",
                    f"  规则: {model.rule_definition or '未填写'}",
                    f"  掌握提示: {model.mastery_hint or '未填写'}",
                ]
                lines.extend(parts)
            if lines:
                ref_blocks.append("【已有概念卡参考】\n" + "\n".join(lines))

        ref_text = ("\n\n".join(ref_blocks) + "\n\n") if ref_blocks else ""
        participant_desc = {
            "concept_names": concept_participants,
            "related_entities": related_entities,
            "all_participants": [p.model_dump(mode="json") for p in participants],
        }
        user_prompt = (
            f"{ref_text}"
            f"参与实体信息：{participant_desc}\n\n"
            f"章节正文如下：\n{text}\n"
        )

        log_extract_prompt("concept_state", self.prompt_name, llm_config_id, system_prompt, user_prompt)

        result = await llm_service.generate_structured(
            session=session,
            llm_config_id=llm_config_id,
            user_prompt=user_prompt,
            output_type=ConceptStateExtraction,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )
        if not isinstance(result, ConceptStateExtraction):
            raise ValueError("概念掌握提取失败：输出格式不符合 ConceptStateExtraction")
        return result

    def persist(
        self,
        *,
        service: Any,
        session: Session,
        project_id: int,
        data: ConceptStateExtraction,
        options: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = context or {}
        concept_card_type = session.exec(select(CardType).where(CardType.name == "概念卡")).first()
        if not concept_card_type:
            raise ValueError("未找到卡片类型：概念卡")

        affected_card_ids: list[int] = []
        updated_card_count = 0

        for concept in data.concepts:
            stmt = select(Card).where(
                Card.project_id == project_id,
                Card.card_type_id == concept_card_type.id,
                Card.title == concept.name,
            )
            card = session.exec(stmt).first()

            if card:
                existing = _load_existing_concept_card(card)
                merged = _merge_concept_card(existing, concept)
                card.title = merged.name
                card.content = merged.model_dump(mode="json")
                flag_modified(card, "content")
            else:
                continue

            session.add(card)
            session.flush()
            if card.id is not None:
                affected_card_ids.append(card.id)
            updated_card_count += 1

        if updated_card_count:
            session.commit()

        if not updated_card_count:
            session.commit()
        return {
            "written": updated_card_count,
            "updated_card_count": updated_card_count,
            "updated_relation_count": 0,
            "affected_card_ids": affected_card_ids,
        }

    def build_affected_targets(self, data: ConceptStateExtraction) -> list[dict[str, Any]]:
        return [
            {"type": "card", "card_type": "概念卡", "title": concept.name}
            for concept in data.concepts
            if concept.name
        ]
