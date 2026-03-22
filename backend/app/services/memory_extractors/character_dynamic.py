from __future__ import annotations

from typing import Any

from sqlmodel import Session

from app.schemas.entity import UpdateDynamicInfo
from app.schemas.memory import ParticipantTyped


class CharacterDynamicExtractor:
    code = "character_dynamic"
    name = "角色动态信息提取"
    target = "card"
    preview_supported = True
    output_model = UpdateDynamicInfo

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
    ) -> UpdateDynamicInfo:
        return await service.extract_dynamic_info_preview(
            text=text,
            participants=participants,
            llm_config_id=llm_config_id,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            project_id=project_id,
            extra_context=extra_context,
        )

    def persist(
        self,
        *,
        service: Any,
        session: Session,
        project_id: int,
        data: UpdateDynamicInfo,
        options: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        queue_size = int((options or {}).get("queue_size") or 5)
        result = service.update_dynamic_character_info(
            project_id=project_id,
            data=data,
            queue_size=queue_size,
        )
        result.setdefault("written", result.get("updated_card_count", 0))
        return result

    def build_affected_targets(self, data: UpdateDynamicInfo) -> list[dict[str, Any]]:
        return [
            {"type": "card", "card_type": "角色卡", "title": item.name}
            for item in data.info_list
            if getattr(item, "name", None)
        ]
