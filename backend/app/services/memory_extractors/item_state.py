from __future__ import annotations

from typing import Any, Iterable, Optional

from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import Session, select

from app.db.models import Card, CardType
from app.schemas.entity import ItemCard
from app.schemas.memory import ItemStateExtraction, ParticipantTyped
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


def _merge_item_card(existing: ItemCard, incoming: ItemCard) -> ItemCard:
    return ItemCard(
        name=incoming.name or existing.name,
        entity_type="item",
        life_span=incoming.life_span or existing.life_span,
        category=_merge_optional_text(existing.category, incoming.category) or "",
        description=_merge_optional_text(existing.description, incoming.description) or "",
        owner_hint=_merge_optional_text(existing.owner_hint, incoming.owner_hint),
        power_or_effect=_merge_optional_text(existing.power_or_effect, incoming.power_or_effect),
        constraints=_merge_optional_text(existing.constraints, incoming.constraints),
        current_state=_merge_optional_text(existing.current_state, incoming.current_state),
        important_events=_unique_keep_order([*(existing.important_events or []), *(incoming.important_events or [])])[:10],
    )


def _load_existing_item_card(card: Card) -> ItemCard:
    payload = dict(card.content or {})
    if not payload.get("name"):
        payload["name"] = card.title
    return ItemCard.model_validate(payload)


class ItemStateExtractor:
    code = "item_state"
    name = "物品状态提取"
    target = "card"
    preview_supported = True
    output_model = ItemStateExtraction
    prompt_name = "物品状态提取"

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
    ) -> ItemStateExtraction:
        prompt = prompt_service.get_prompt_by_name(session, self.prompt_name)
        if not prompt:
            raise ValueError(f"未找到提示词: {self.prompt_name}")

        system_prompt = prompt.template
        schema_json = ItemStateExtraction.model_json_schema()
        system_prompt += f"\n\n请严格按照以下 JSON Schema 输出：\n{schema_json}"

        item_participants = [p.name for p in participants if p.type == "item"]
        owner_participants = [p.name for p in participants if p.type in {"character", "organization"}]

        ref_blocks: list[str] = []
        if extra_context:
            ref_blocks.append(f"【补充上下文，仅供参考，不要机械复述】\n{extra_context}")

        if project_id and item_participants:
            item_card_type = session.exec(select(CardType).where(CardType.name == "物品卡")).first()
            rows = []
            if item_card_type:
                stmt = select(Card).where(
                    Card.project_id == project_id,
                    Card.card_type_id == item_card_type.id,
                    Card.title.in_(item_participants),
                )
                rows = session.exec(stmt).all()
            lines: list[str] = []
            for card in rows:
                try:
                    model = _load_existing_item_card(card)
                except Exception:
                    continue
                parts = [
                    f"- {model.name}",
                    f"  类别: {model.category or '未填写'}",
                    f"  当前状态: {model.current_state or '未填写'}",
                    f"  作用: {model.power_or_effect or '未填写'}",
                ]
                lines.extend(parts)
            if lines:
                ref_blocks.append("【已有物品卡参考】\n" + "\n".join(lines))

        ref_text = ("\n\n".join(ref_blocks) + "\n\n") if ref_blocks else ""
        participant_desc = {
            "item_names": item_participants,
            "owner_names": owner_participants,
            "all_participants": [p.model_dump(mode="json") for p in participants],
        }
        user_prompt = (
            f"{ref_text}"
            f"参与实体信息：{participant_desc}\n\n"
            f"章节正文如下：\n{text}\n"
        )

        log_extract_prompt("item_state", self.prompt_name, llm_config_id, system_prompt, user_prompt)

        result = await llm_service.generate_structured(
            session=session,
            llm_config_id=llm_config_id,
            user_prompt=user_prompt,
            output_type=ItemStateExtraction,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )
        if not isinstance(result, ItemStateExtraction):
            raise ValueError("物品状态提取失败：输出格式不符合 ItemStateExtraction")
        return result

    def persist(
        self,
        *,
        service: Any,
        session: Session,
        project_id: int,
        data: ItemStateExtraction,
        options: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = context or {}
        item_card_type = session.exec(select(CardType).where(CardType.name == "物品卡")).first()
        if not item_card_type:
            raise ValueError("未找到卡片类型：物品卡")

        affected_card_ids: list[int] = []
        updated_card_count = 0

        for item in data.items:
            stmt = select(Card).where(
                Card.project_id == project_id,
                Card.card_type_id == item_card_type.id,
                Card.title == item.name,
            )
            card = session.exec(stmt).first()

            if card:
                existing = _load_existing_item_card(card)
                merged = _merge_item_card(existing, item)
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

    def build_affected_targets(self, data: ItemStateExtraction) -> list[dict[str, Any]]:
        return [
            {"type": "card", "card_type": "物品卡", "title": item.name}
            for item in data.items
            if item.name
        ]
