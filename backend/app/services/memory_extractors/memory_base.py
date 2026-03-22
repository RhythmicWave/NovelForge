from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional, Protocol

from loguru import logger
from pydantic import BaseModel
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import Session, select

from app.db.models import Card, CardType
from app.schemas.memory import ParticipantTyped
from app.services import prompt_service
from app.services.ai.core import llm_service


def log_extract_prompt(
    tag: str,
    prompt_name: Optional[str],
    llm_config_id: int,
    system_prompt: str,
    user_prompt: str,
) -> None:
    logger.info(
        f"[MemoryExtractPrompt][{tag}] prompt_name={prompt_name!r} llm_config_id={llm_config_id}\n"
        f"[system_prompt]\n{system_prompt}\n"
        f"[user_prompt]\n{user_prompt}"
    )


def unique_keep_order(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def merge_optional_text(old: Optional[str], new: Optional[str]) -> Optional[str]:
    new_value = (new or "").strip()
    if new_value:
        return new_value
    old_value = (old or "").strip()
    return old_value or None


@dataclass(frozen=True)
class StructuredCardExtractorSpec:
    code: str
    name: str
    prompt_name: str
    card_type_name: str
    output_model: type[BaseModel]
    list_field_name: str
    target_participant_types: tuple[str, ...]
    related_participant_types: tuple[str, ...]
    target_participant_key: str
    related_participant_key: str
    reference_title: str


class StructuredCardMemoryExtractor:
    target = "card"
    preview_supported = True

    def __init__(self, spec: StructuredCardExtractorSpec):
        self.spec = spec
        self.code = spec.code
        self.name = spec.name
        self.prompt_name = spec.prompt_name
        self.output_model = spec.output_model

    def load_existing_card(self, card: Card) -> BaseModel:
        raise NotImplementedError

    def merge_card(self, existing: BaseModel, incoming: BaseModel) -> BaseModel:
        raise NotImplementedError

    def build_reference_lines(self, model: BaseModel) -> list[str]:
        raise NotImplementedError

    def build_participant_payload(
        self,
        target_names: list[str],
        related_names: list[str],
        participants: list[ParticipantTyped],
    ) -> dict[str, Any]:
        return {
            self.spec.target_participant_key: target_names,
            self.spec.related_participant_key: related_names,
            "all_participants": [p.model_dump(mode="json") for p in participants],
        }

    def get_items(self, data: BaseModel) -> list[Any]:
        return list(getattr(data, self.spec.list_field_name, []) or [])

    def set_items(self, data: BaseModel, items: list[Any]) -> None:
        setattr(data, self.spec.list_field_name, items)

    def get_item_name(self, item: Any) -> str:
        return str(getattr(item, "name", "") or "").strip()

    def _partition_participants(self, participants: list[ParticipantTyped]) -> tuple[list[str], list[str]]:
        target_names = unique_keep_order(
            p.name for p in participants if p.type in self.spec.target_participant_types
        )
        target_name_set = set(target_names)
        related_names = unique_keep_order(
            p.name
            for p in participants
            if p.type in self.spec.related_participant_types and p.name not in target_name_set
        )
        return target_names, related_names

    def _build_reference_block(
        self,
        *,
        session: Session,
        project_id: int | None,
        target_names: list[str],
    ) -> str | None:
        if not project_id or not target_names:
            return None
        card_type = session.exec(select(CardType).where(CardType.name == self.spec.card_type_name)).first()
        if not card_type:
            return None
        stmt = select(Card).where(
            Card.project_id == project_id,
            Card.card_type_id == card_type.id,
            Card.title.in_(target_names),
        )
        rows = session.exec(stmt).all()
        lines: list[str] = []
        for card in rows:
            try:
                model = self.load_existing_card(card)
            except Exception:
                continue
            lines.extend(self.build_reference_lines(model))
        if not lines:
            return None
        return f"【{self.spec.reference_title}】\n" + "\n".join(lines)

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
    ) -> BaseModel:
        prompt = prompt_service.get_prompt_by_name(session, self.prompt_name)
        if not prompt:
            raise ValueError(f"未找到提示词: {self.prompt_name}")

        system_prompt = prompt.template
        system_prompt += f"\n\n请严格按以下 JSON Schema 输出:\n{self.output_model.model_json_schema()}"

        target_names, related_names = self._partition_participants(participants)

        ref_blocks: list[str] = []
        if extra_context:
            ref_blocks.append(f"【补充上下文，仅供参考，不要机械复述】\n{extra_context}")

        reference_block = self._build_reference_block(
            session=session,
            project_id=project_id,
            target_names=target_names,
        )
        if reference_block:
            ref_blocks.append(reference_block)

        ref_text = ("\n\n".join(ref_blocks) + "\n\n") if ref_blocks else ""
        participant_desc = self.build_participant_payload(target_names, related_names, participants)
        user_prompt = (
            f"{ref_text}"
            f"参与实体信息：{participant_desc}\n\n"
            f"章节正文如下：\n{text}\n"
        )

        log_extract_prompt(self.code, self.prompt_name, llm_config_id, system_prompt, user_prompt)

        result = await llm_service.generate_structured(
            session=session,
            llm_config_id=llm_config_id,
            user_prompt=user_prompt,
            output_type=self.output_model,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )
        if not isinstance(result, self.output_model):
            raise ValueError(f"{self.name}失败：输出格式不符合 {self.output_model.__name__}")

        if target_names:
            allowed_names = {name.strip() for name in target_names if name.strip()}
            filtered_items = [
                item for item in self.get_items(result)
                if self.get_item_name(item) in allowed_names
            ]
            self.set_items(result, filtered_items)
        return result

    def persist(
        self,
        *,
        service: Any,
        session: Session,
        project_id: int,
        data: BaseModel,
        options: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        card_type = session.exec(select(CardType).where(CardType.name == self.spec.card_type_name)).first()
        if not card_type:
            raise ValueError(f"未找到卡片类型：{self.spec.card_type_name}")

        affected_card_ids: list[int] = []
        updated_card_count = 0

        for item in self.get_items(data):
            item_name = self.get_item_name(item)
            if not item_name:
                continue
            stmt = select(Card).where(
                Card.project_id == project_id,
                Card.card_type_id == card_type.id,
                Card.title == item_name,
            )
            card = session.exec(stmt).first()
            if not card:
                continue

            existing = self.load_existing_card(card)
            merged = self.merge_card(existing, item)
            card.title = self.get_item_name(merged) or card.title
            card.content = merged.model_dump(mode="json")
            flag_modified(card, "content")
            session.add(card)
            session.flush()
            if card.id is not None:
                affected_card_ids.append(card.id)
            updated_card_count += 1

        session.commit()
        return {
            "written": updated_card_count,
            "updated_card_count": updated_card_count,
            "updated_relation_count": 0,
            "affected_card_ids": affected_card_ids,
        }

    def build_affected_targets(self, data: BaseModel) -> list[dict[str, Any]]:
        return [
            {"type": "card", "card_type": self.spec.card_type_name, "title": self.get_item_name(item)}
            for item in self.get_items(data)
            if self.get_item_name(item)
        ]

class BaseMemoryExtractor(Protocol):
    code: str
    name: str
    target: str
    preview_supported: bool
    output_model: type[BaseModel]

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
    ) -> BaseModel: ...

    def persist(
        self,
        *,
        service: Any,
        session: Session,
        project_id: int,
        data: BaseModel,
        options: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def build_affected_targets(self, data: BaseModel) -> list[dict[str, Any]]: ...
