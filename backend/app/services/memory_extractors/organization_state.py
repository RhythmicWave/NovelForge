from __future__ import annotations

from typing import Any, Iterable, Optional

from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import Session, select

from app.db.models import Card, CardType
from app.schemas.entity import OrganizationCard, OrganizationCardMemory
from app.schemas.memory import OrganizationStateExtraction, ParticipantTyped
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


def _merge_organization_card(existing: OrganizationCard, incoming: OrganizationCardMemory) -> OrganizationCard:
    return OrganizationCard(
        name=incoming.name or existing.name,
        entity_type="organization",
        life_span=incoming.life_span or existing.life_span,
        description=_merge_optional_text(existing.description, incoming.description) or "",
        influence=_merge_optional_text(existing.influence, incoming.influence),
        relationship=_unique_keep_order([*(existing.relationship or []), *(incoming.relationship or [])])[:12],
        dynamic_state=_unique_keep_order([*(existing.dynamic_state or []), *(incoming.dynamic_state or [])])[-8:],
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


class OrganizationStateExtractor:
    code = "organization_state"
    name = "组织状态提取"
    target = "card"
    preview_supported = True
    output_model = OrganizationStateExtraction
    prompt_name = "组织状态提取"

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
    ) -> OrganizationStateExtraction:
        prompt = prompt_service.get_prompt_by_name(session, self.prompt_name)
        if not prompt:
            raise ValueError(f"未找到提示词: {self.prompt_name}")

        system_prompt = prompt.template
        system_prompt += f"\n\n请严格按以下 JSON Schema 输出:\n{OrganizationStateExtraction.model_json_schema()}"

        organization_names = [p.name for p in participants if p.type == "organization"]
        related_entities = [
            p.name
            for p in participants
            if p.type in {"character", "organization", "scene", "item", "concept"} and p.name not in organization_names
        ]

        ref_blocks: list[str] = []
        if extra_context:
            ref_blocks.append(f"【补充上下文，仅供参考，不要机械复述】\n{extra_context}")

        if project_id and organization_names:
            organization_card_type = session.exec(select(CardType).where(CardType.name == "组织卡")).first()
            rows = []
            if organization_card_type:
                stmt = select(Card).where(
                    Card.project_id == project_id,
                    Card.card_type_id == organization_card_type.id,
                    Card.title.in_(organization_names),
                )
                rows = session.exec(stmt).all()
            lines: list[str] = []
            for card in rows:
                try:
                    model = _load_existing_organization_card(card)
                except Exception:
                    continue
                lines.extend(
                    [
                        f"- {model.name}",
                        f"  简介: {model.description or '未填写'}",
                        f"  当前影响力: {model.influence or '未填写'}",
                        f"  对外关系: {'；'.join(model.relationship or []) or '暂无'}",
                        f"  当前状态: {'；'.join(model.dynamic_state or []) or '暂无'}",
                    ]
                )
            if lines:
                ref_blocks.append("【已有组织卡参考】\n" + "\n".join(lines))

        ref_text = ("\n\n".join(ref_blocks) + "\n\n") if ref_blocks else ""
        participant_desc = {
            "organization_names": organization_names,
            "related_entities": related_entities,
            "all_participants": [p.model_dump(mode="json") for p in participants],
        }
        user_prompt = (
            f"{ref_text}"
            f"参与实体信息：{participant_desc}\n\n"
            f"章节正文如下：\n{text}\n"
        )

        log_extract_prompt("organization_state", self.prompt_name, llm_config_id, system_prompt, user_prompt)

        result = await llm_service.generate_structured(
            session=session,
            llm_config_id=llm_config_id,
            user_prompt=user_prompt,
            output_type=OrganizationStateExtraction,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )
        if not isinstance(result, OrganizationStateExtraction):
            raise ValueError("组织状态提取失败：输出格式不符合 OrganizationStateExtraction")
        if organization_names:
            organization_name_set = {name.strip() for name in organization_names if name.strip()}
            result.organizations = [
                item for item in result.organizations if (item.name or "").strip() in organization_name_set
            ]
        return result

    def persist(
        self,
        *,
        service: Any,
        session: Session,
        project_id: int,
        data: OrganizationStateExtraction,
        options: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = context or {}
        organization_card_type = session.exec(select(CardType).where(CardType.name == "组织卡")).first()
        if not organization_card_type:
            raise ValueError("未找到卡片类型：组织卡")

        affected_card_ids: list[int] = []
        updated_card_count = 0

        for organization in data.organizations:
            stmt = select(Card).where(
                Card.project_id == project_id,
                Card.card_type_id == organization_card_type.id,
                Card.title == organization.name,
            )
            card = session.exec(stmt).first()
            if not card:
                continue

            existing = _load_existing_organization_card(card)
            merged = _merge_organization_card(existing, organization)
            card.title = merged.name
            card.content = merged.model_dump(mode="json")
            flag_modified(card, "content")
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

    def build_affected_targets(self, data: OrganizationStateExtraction) -> list[dict[str, Any]]:
        return [
            {"type": "card", "card_type": "组织卡", "title": item.name}
            for item in data.organizations
            if item.name
        ]
