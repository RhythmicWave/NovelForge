from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Any, Dict, List, Tuple

from sqlmodel import Session

from app.schemas.relation_extract import CN_TO_EN_KIND, EN_TO_CN_KIND
from app.schemas.relation_graph import (
    RelationGraphBatchAppendEventsRequest,
    RelationGraphBatchCreateRequest,
    RelationGraphBatchDeleteRequest,
    RelationGraphBatchUpdateKindRequest,
    RelationGraphBatchUpdateStanceRequest,
    RelationGraphDeleteRequest,
    RelationGraphExportRequest,
    RelationGraphExportResponse,
    RelationGraphImportRequest,
    RelationGraphImportResponse,
    RelationGraphInput,
    RelationGraphListRequest,
    RelationGraphListResponse,
    RelationGraphRecord,
    RelationGraphUpsertRequest,
    RelationGraphWriteResponse,
)
from app.services.kg_provider import KnowledgeGraphProvider, get_provider


class RelationGraphService:
    def __init__(self, session: Session, graph_provider: KnowledgeGraphProvider | None = None):
        self.session = session
        self.graph = graph_provider or get_provider()

    def _resolve_kind_en(self, relation: RelationGraphInput) -> str:
        if relation.kind_en and relation.kind_en.strip():
            return relation.kind_en.strip()

        kind_cn = (relation.kind_cn or relation.kind or "").strip()
        if kind_cn in CN_TO_EN_KIND:
            return CN_TO_EN_KIND[kind_cn]
        if kind_cn in EN_TO_CN_KIND:
            return kind_cn

        raise ValueError("Invalid relation kind: provide kind_en or valid kind_cn")

    def _resolve_kind_cn(self, kind_en: str, relation: RelationGraphInput) -> str:
        kind_cn = (relation.kind_cn or relation.kind or "").strip()
        if kind_cn:
            return kind_cn
        return EN_TO_CN_KIND.get(kind_en, kind_en)

    def _to_provider_relation(self, relation: RelationGraphInput) -> Dict[str, Any]:
        kind_en = self._resolve_kind_en(relation)
        kind_cn = self._resolve_kind_cn(kind_en, relation)

        return {
            "source": relation.source.strip(),
            "target": relation.target.strip(),
            "kind_en": kind_en,
            "kind_cn": kind_cn,
            "fact": relation.fact,
            "a_to_b_addressing": relation.a_to_b_addressing,
            "b_to_a_addressing": relation.b_to_a_addressing,
            "recent_dialogues": relation.recent_dialogues,
            "recent_event_summaries": [event.model_dump(exclude_none=True) for event in relation.recent_event_summaries],
            "stance": relation.stance,
        }

    @staticmethod
    def _to_record(row: Dict[str, Any]) -> RelationGraphRecord:
        return RelationGraphRecord.model_validate(
            {
                "source": row.get("source") or row.get("a"),
                "target": row.get("target") or row.get("b"),
                "kind_en": row.get("kind_en"),
                "kind_cn": row.get("kind_cn") or row.get("kind"),
                "kind": row.get("kind") or row.get("kind_cn"),
                "fact": row.get("fact"),
                "a_to_b_addressing": row.get("a_to_b_addressing"),
                "b_to_a_addressing": row.get("b_to_a_addressing"),
                "recent_dialogues": row.get("recent_dialogues") or [],
                "recent_event_summaries": row.get("recent_event_summaries") or [],
                "stance": row.get("stance"),
                "updated_at": row.get("updated_at"),
            }
        )

    def list_relations(self, req: RelationGraphListRequest) -> RelationGraphListResponse:
        data = self.graph.list_relations(
            project_id=req.project_id,
            keyword=req.keyword,
            kinds=req.kinds or None,
            stances=req.stances or None,
            offset=req.offset,
            limit=req.limit,
        )
        items = [self._to_record(row) for row in (data.get("items") or [])]
        return RelationGraphListResponse(items=items, total=int(data.get("total") or 0))

    def upsert_relation(self, req: RelationGraphUpsertRequest) -> RelationGraphRecord:
        payload = self._to_provider_relation(req.relation)
        row = self.graph.upsert_relation(req.project_id, payload)
        return self._to_record(row)

    def delete_relation(self, req: RelationGraphDeleteRequest) -> RelationGraphWriteResponse:
        affected = self.graph.delete_relation(req.project_id, req.key.source, req.key.target, req.key.kind_en)
        return RelationGraphWriteResponse(affected=affected)

    def batch_delete_relations(self, req: RelationGraphBatchDeleteRequest) -> RelationGraphWriteResponse:
        affected = self.graph.batch_delete_relations(req.project_id, [key.model_dump() for key in req.keys])
        return RelationGraphWriteResponse(affected=affected)

    def batch_update_kind(self, req: RelationGraphBatchUpdateKindRequest) -> RelationGraphWriteResponse:
        new_kind_en = (req.new_kind_en or "").strip()
        new_kind_cn = (req.new_kind_cn or "").strip() or None
        if not new_kind_en:
            if not new_kind_cn:
                raise ValueError("new_kind_en or new_kind_cn is required")
            if new_kind_cn in CN_TO_EN_KIND:
                new_kind_en = CN_TO_EN_KIND[new_kind_cn]
            elif new_kind_cn in EN_TO_CN_KIND:
                new_kind_en = new_kind_cn
            else:
                raise ValueError("Invalid new_kind_cn")

        affected = self.graph.batch_update_kind(
            req.project_id,
            [key.model_dump() for key in req.keys],
            new_kind_en=new_kind_en,
            new_kind_cn=new_kind_cn or EN_TO_CN_KIND.get(new_kind_en, new_kind_en),
        )
        return RelationGraphWriteResponse(affected=affected)

    def batch_update_stance(self, req: RelationGraphBatchUpdateStanceRequest) -> RelationGraphWriteResponse:
        affected = self.graph.batch_update_stance(
            req.project_id,
            [key.model_dump() for key in req.keys],
            stance=req.stance,
        )
        return RelationGraphWriteResponse(affected=affected)

    def batch_append_events(self, req: RelationGraphBatchAppendEventsRequest) -> RelationGraphWriteResponse:
        affected = self.graph.batch_append_events(
            req.project_id,
            [key.model_dump() for key in req.keys],
            events=[event.model_dump(exclude_none=True) for event in req.events],
            max_size=req.max_size,
        )
        return RelationGraphWriteResponse(affected=affected)

    def batch_create_relations(self, req: RelationGraphBatchCreateRequest) -> RelationGraphWriteResponse:
        affected = 0
        for relation in req.relations:
            payload = self._to_provider_relation(relation)
            self.graph.upsert_relation(req.project_id, payload)
            affected += 1
        return RelationGraphWriteResponse(affected=affected)

    def _snapshot_keys(self, project_id: int) -> set[Tuple[str, str, str]]:
        rows = self.graph.list_relations(project_id=project_id, offset=0, limit=200000).get("items") or []
        return {
            (
                str(row.get("source") or row.get("a") or "").strip(),
                str(row.get("target") or row.get("b") or "").strip(),
                str(row.get("kind_en") or "").strip(),
            )
            for row in rows
            if str(row.get("source") or row.get("a") or "").strip()
            and str(row.get("target") or row.get("b") or "").strip()
            and str(row.get("kind_en") or "").strip()
        }

    def export_relations(self, req: RelationGraphExportRequest) -> RelationGraphExportResponse:
        rows = self.graph.list_relations(project_id=req.project_id, offset=0, limit=200000).get("items") or []

        if req.keys:
            key_set = {(key.source, key.target, key.kind_en) for key in req.keys}
            rows = [
                row
                for row in rows
                if (
                    str(row.get("source") or row.get("a") or "").strip(),
                    str(row.get("target") or row.get("b") or "").strip(),
                    str(row.get("kind_en") or "").strip(),
                )
                in key_set
            ]

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        if req.format == "json":
            content = json.dumps(rows, ensure_ascii=False, indent=2)
            return RelationGraphExportResponse(
                filename=f"relation-graph-{req.project_id}-{stamp}.json",
                mime_type="application/json",
                content=content,
            )

        output = io.StringIO()
        fieldnames = [
            "source",
            "target",
            "kind_en",
            "kind_cn",
            "fact",
            "a_to_b_addressing",
            "b_to_a_addressing",
            "stance",
            "recent_dialogues",
            "recent_event_summaries",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "source": row.get("source") or row.get("a") or "",
                    "target": row.get("target") or row.get("b") or "",
                    "kind_en": row.get("kind_en") or "",
                    "kind_cn": row.get("kind_cn") or row.get("kind") or "",
                    "fact": row.get("fact") or "",
                    "a_to_b_addressing": row.get("a_to_b_addressing") or "",
                    "b_to_a_addressing": row.get("b_to_a_addressing") or "",
                    "stance": row.get("stance") or "",
                    "recent_dialogues": json.dumps(row.get("recent_dialogues") or [], ensure_ascii=False),
                    "recent_event_summaries": json.dumps(row.get("recent_event_summaries") or [], ensure_ascii=False),
                }
            )
        return RelationGraphExportResponse(
            filename=f"relation-graph-{req.project_id}-{stamp}.csv",
            mime_type="text/csv",
            content=output.getvalue(),
        )

    @staticmethod
    def _parse_json_list_field(value: Any, field_name: str) -> List[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            try:
                parsed = json.loads(text)
            except Exception as exc:
                raise ValueError(f"Invalid JSON in {field_name}: {exc}")
            if not isinstance(parsed, list):
                raise ValueError(f"Invalid JSON list in {field_name}")
            return parsed
        raise ValueError(f"Invalid value type in {field_name}")

    def _normalize_import_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "source": row.get("source") or row.get("a"),
            "target": row.get("target") or row.get("b"),
            "kind_en": row.get("kind_en"),
            "kind_cn": row.get("kind_cn") or row.get("kind"),
            "fact": row.get("fact"),
            "a_to_b_addressing": row.get("a_to_b_addressing"),
            "b_to_a_addressing": row.get("b_to_a_addressing"),
            "recent_dialogues": self._parse_json_list_field(row.get("recent_dialogues"), "recent_dialogues"),
            "recent_event_summaries": self._parse_json_list_field(row.get("recent_event_summaries"), "recent_event_summaries"),
            "stance": row.get("stance"),
        }

    def _parse_import_rows(self, req: RelationGraphImportRequest) -> List[RelationGraphInput]:
        if req.format == "json":
            raw = json.loads(req.content)
            if isinstance(raw, dict) and isinstance(raw.get("relations"), list):
                raw = raw["relations"]
            if not isinstance(raw, list):
                raise ValueError("JSON import content must be a list")
            return [RelationGraphInput.model_validate(self._normalize_import_row(row)) for row in raw]

        reader = csv.DictReader(io.StringIO(req.content))
        rows: List[RelationGraphInput] = []
        for row in reader:
            rows.append(RelationGraphInput.model_validate(self._normalize_import_row(row)))
        return rows

    def import_relations(self, req: RelationGraphImportRequest) -> RelationGraphImportResponse:
        existing = self._snapshot_keys(req.project_id)
        created = 0
        updated = 0
        failed = 0
        errors: List[str] = []

        relations = self._parse_import_rows(req)
        for idx, relation in enumerate(relations, start=1):
            try:
                payload = self._to_provider_relation(relation)
                key = (payload["source"], payload["target"], payload["kind_en"])
                self.graph.upsert_relation(req.project_id, payload)
                if key in existing:
                    updated += 1
                else:
                    created += 1
                    existing.add(key)
            except Exception as exc:
                failed += 1
                errors.append(f"row {idx}: {exc}")

        return RelationGraphImportResponse(created=created, updated=updated, failed=failed, errors=errors)
