from __future__ import annotations

from typing import Any

from sqlmodel import Session

from app.schemas.memory import ParticipantTyped
from app.schemas.relation_extract import RelationExtraction


class RelationExtractor:
    code = "relation"
    name = "关系提取"
    target = "graph"
    preview_supported = True
    output_model = RelationExtraction

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
    ) -> RelationExtraction:
        return await service.extract_relations_preview(
            text=text,
            participants=participants,
            llm_config_id=llm_config_id,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )

    def persist(
        self,
        *,
        service: Any,
        session: Session,
        project_id: int,
        data: RelationExtraction,
        options: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = context or {}
        result = service.ingest_relations_from_llm(
            project_id,
            data,
            volume_number=context.get("volume_number"),
            chapter_number=context.get("chapter_number"),
            participants_with_type=context.get("participants"),
        )
        result.setdefault("updated_relation_count", result.get("written", 0))
        return result

    def build_affected_targets(self, data: RelationExtraction) -> list[dict[str, Any]]:
        return [
            {"type": "graph", "source": relation.a, "target": relation.b, "kind": relation.kind}
            for relation in data.relations
        ]
