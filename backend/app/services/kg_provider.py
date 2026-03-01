from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol, Tuple

from sqlalchemy import delete
from sqlmodel import Session, select

from app.schemas.relation_extract import EN_TO_CN_KIND


DEFAULT_KIND_CN = "其他"


class KnowledgeGraphUnavailableError(RuntimeError):
    pass


def _ensure_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def _ensure_string_list(value: Any) -> List[str]:
    return [str(item).strip() for item in _ensure_list(value) if isinstance(item, str) and str(item).strip()]


def _ensure_event_list(value: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in _ensure_list(value):
        if hasattr(item, "model_dump"):
            item = item.model_dump()
        if not isinstance(item, dict):
            continue
        summary = str(item.get("summary") or "").strip()
        if not summary:
            continue
        normalized: Dict[str, Any] = {"summary": summary}
        if item.get("volume_number") is not None:
            try:
                normalized["volume_number"] = int(item["volume_number"])
            except Exception:
                pass
        if item.get("chapter_number") is not None:
            try:
                normalized["chapter_number"] = int(item["chapter_number"])
            except Exception:
                pass
        out.append(normalized)
    return out


def _extract_stance_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    if isinstance(value, dict):
        for key in ("value", "stance", "label", "name"):
            raw = value.get(key)
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
    return None


def _stance_to_storage(value: Any) -> Optional[Dict[str, Any]]:
    stance = _extract_stance_value(value)
    return {"value": stance} if stance else None


def _normalize_keys(keys: List[Dict[str, Any]]) -> List[Tuple[str, str, str]]:
    out: List[Tuple[str, str, str]] = []
    for key in keys or []:
        if not isinstance(key, dict):
            continue
        source = str(key.get("source") or key.get("a") or "").strip()
        target = str(key.get("target") or key.get("b") or "").strip()
        kind_en = str(key.get("kind_en") or "").strip()
        if source and target and kind_en:
            out.append((source, target, kind_en))
    return out


def _event_identity(event: Dict[str, Any]) -> Tuple[str, Optional[int], Optional[int]]:
    return (str(event.get("summary") or "").strip(), event.get("volume_number"), event.get("chapter_number"))


def _merge_events(existing: List[Dict[str, Any]], incoming: List[Dict[str, Any]], max_size: int = 20) -> List[Dict[str, Any]]:
    seen = set()
    merged: List[Dict[str, Any]] = []
    for item in (existing or []) + (incoming or []):
        key = _event_identity(item)
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    if len(merged) > max_size:
        return merged[-max_size:]
    return merged


def _relation_matches_filters(item: Dict[str, Any], keyword: Optional[str], kinds: Optional[List[str]], stances: Optional[List[str]]) -> bool:
    if kinds:
        kind_set = {str(kind).strip() for kind in kinds if str(kind).strip()}
        if kind_set and str(item.get("kind_cn") or "") not in kind_set:
            return False
    if stances:
        stance_set = {str(stance).strip() for stance in stances if str(stance).strip()}
        if stance_set and str(item.get("stance") or "") not in stance_set:
            return False
    if keyword:
        needle = keyword.strip().lower()
        if needle:
            hay = " ".join([
                str(item.get("source") or ""),
                str(item.get("target") or ""),
                str(item.get("kind_cn") or ""),
                str(item.get("fact") or ""),
            ]).lower()
            if needle not in hay:
                return False
    return True


def _build_relation_item(
    *,
    source: str,
    target: str,
    kind_en: str,
    kind_cn: Optional[str],
    fact: Optional[str],
    a_to_b_addressing: Optional[str],
    b_to_a_addressing: Optional[str],
    recent_dialogues: Any,
    recent_event_summaries: Any,
    stance: Any,
    updated_at: Optional[str] = None,
) -> Dict[str, Any]:
    resolved_kind_cn = str(kind_cn or EN_TO_CN_KIND.get(kind_en, kind_en) or DEFAULT_KIND_CN)
    return {
        "source": source,
        "target": target,
        "a": source,
        "b": target,
        "kind_en": kind_en,
        "kind_cn": resolved_kind_cn,
        "kind": resolved_kind_cn,
        "fact": fact or f"{source} {kind_en} {target}",
        "a_to_b_addressing": a_to_b_addressing,
        "b_to_a_addressing": b_to_a_addressing,
        "recent_dialogues": _ensure_string_list(recent_dialogues),
        "recent_event_summaries": _ensure_event_list(recent_event_summaries),
        "stance": _extract_stance_value(stance),
        "updated_at": updated_at,
    }


class KnowledgeGraphProvider(Protocol):
    def ingest_aliases(self, project_id: int, mapping: Dict[str, List[str]]) -> None: ...

    def ingest_triples_with_attributes(self, project_id: int, triples: List[Tuple[str, str, str, Dict[str, Any]]]) -> None: ...

    def query_subgraph(
        self,
        project_id: int,
        participants: Optional[List[str]] = None,
        radius: int = 2,
        edge_type_whitelist: Optional[List[str]] = None,
        top_k: int = 50,
        max_chapter_id: Optional[int] = None,
    ) -> Dict[str, Any]: ...

    def list_relations(
        self,
        project_id: int,
        *,
        keyword: Optional[str] = None,
        kinds: Optional[List[str]] = None,
        stances: Optional[List[str]] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> Dict[str, Any]: ...

    def upsert_relation(self, project_id: int, relation: Dict[str, Any]) -> Dict[str, Any]: ...

    def delete_relation(self, project_id: int, source: str, target: str, kind_en: str) -> int: ...

    def batch_delete_relations(self, project_id: int, keys: List[Dict[str, Any]]) -> int: ...

    def batch_update_kind(
        self,
        project_id: int,
        keys: List[Dict[str, Any]],
        *,
        new_kind_en: str,
        new_kind_cn: Optional[str] = None,
    ) -> int: ...

    def batch_update_stance(self, project_id: int, keys: List[Dict[str, Any]], *, stance: Optional[str]) -> int: ...

    def batch_append_events(
        self,
        project_id: int,
        keys: List[Dict[str, Any]],
        *,
        events: List[Dict[str, Any]],
        max_size: int = 20,
    ) -> int: ...

    def delete_project_graph(self, project_id: int) -> None: ...

class Neo4jKGProvider:
    def __init__(self) -> None:
        try:
            from neo4j import GraphDatabase  # type: ignore
        except ImportError as exc:
            raise KnowledgeGraphUnavailableError("neo4j dependency not installed") from exc

        from app.core.config import settings

        uri = settings.neo4j.get_uri()
        user = settings.neo4j.get_user()
        password = settings.neo4j.get_password()
        self._driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self) -> None:
        try:
            self._driver.close()
        except Exception:
            pass

    @staticmethod
    def _group(project_id: int) -> str:
        return f"proj:{project_id}"

    def _parse_relation_item(self, source: str, target: str, props: Dict[str, Any]) -> Dict[str, Any]:
        events_raw = props.get("recent_event_summaries")
        if not events_raw and props.get("recent_event_summaries_json"):
            events_raw = props.get("recent_event_summaries_json")

        stance_raw: Any = props.get("stance_value")
        if not stance_raw and props.get("stance_json"):
            try:
                stance_raw = json.loads(props.get("stance_json") or "null")
            except Exception:
                stance_raw = None

        updated_at = None
        if isinstance(props.get("updated_at_epoch"), (int, float)):
            try:
                updated_at = datetime.fromtimestamp(float(props["updated_at_epoch"]) / 1000.0).isoformat()
            except Exception:
                updated_at = None

        return _build_relation_item(
            source=source,
            target=target,
            kind_en=str(props.get("kind_en") or ""),
            kind_cn=props.get("kind") or props.get("kind_cn"),
            fact=props.get("fact"),
            a_to_b_addressing=props.get("a_to_b_addressing"),
            b_to_a_addressing=props.get("b_to_a_addressing"),
            recent_dialogues=props.get("recent_dialogues"),
            recent_event_summaries=events_raw,
            stance=stance_raw,
            updated_at=updated_at,
        )

    def _get_relation(self, project_id: int, source: str, target: str, kind_en: str) -> Optional[Dict[str, Any]]:
        group = self._group(project_id)
        cypher = (
            "MATCH (a:Entity {group_id:$group, name:$source})-[r:RELATES_TO]->(b:Entity {group_id:$group, name:$target}) "
            "WHERE (r.group_id = $group OR r.group_id IS NULL) AND r.kind_en = $kind_en "
            "RETURN a.name AS source, b.name AS target, r {.*} AS props LIMIT 1"
        )
        with self._driver.session() as sess:
            rec = sess.run(cypher, group=group, source=source, target=target, kind_en=kind_en).single()
            if not rec:
                return None
            return self._parse_relation_item(rec["source"], rec["target"], rec["props"] or {})

    def ingest_aliases(self, project_id: int, mapping: Dict[str, List[str]]) -> None:
        return None

    def ingest_triples_with_attributes(self, project_id: int, triples: List[Tuple[str, str, str, Dict[str, Any]]]) -> None:
        for source, kind_en, target, attrs in triples or []:
            attrs = attrs or {}
            self.upsert_relation(
                project_id,
                {
                    "source": source,
                    "target": target,
                    "kind_en": kind_en,
                    "kind_cn": EN_TO_CN_KIND.get(kind_en, kind_en),
                    "fact": f"{source} {kind_en} {target}",
                    "a_to_b_addressing": attrs.get("a_to_b_addressing"),
                    "b_to_a_addressing": attrs.get("b_to_a_addressing"),
                    "recent_dialogues": attrs.get("recent_dialogues") or [],
                    "recent_event_summaries": attrs.get("recent_event_summaries") or [],
                    "stance": attrs.get("stance"),
                },
            )

    def query_subgraph(
        self,
        project_id: int,
        participants: Optional[List[str]] = None,
        radius: int = 2,
        edge_type_whitelist: Optional[List[str]] = None,
        top_k: int = 50,
        max_chapter_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        group = self._group(project_id)
        parts = [p for p in (participants or []) if isinstance(p, str) and p.strip()]
        if not parts:
            return {"nodes": [], "edges": [], "alias_table": {}, "fact_summaries": [], "relation_summaries": []}

        cypher = (
            "MATCH (a:Entity {group_id:$group})-[r:RELATES_TO]->(b:Entity {group_id:$group}) "
            "WHERE a.name IN $parts AND b.name IN $parts AND (r.group_id = $group OR r.group_id IS NULL) "
            "RETURN a.name AS source, b.name AS target, r {.*} AS props LIMIT $limit"
        )

        fact_summaries: List[str] = []
        rel_items: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        edges: List[Dict[str, Any]] = []
        with self._driver.session() as sess:
            for rec in sess.run(cypher, group=group, parts=parts, limit=max(1, int(top_k))):
                source = rec["source"]
                target = rec["target"]
                item = self._parse_relation_item(source, target, rec["props"] or {})
                key = (source, target, str(item.get("kind") or DEFAULT_KIND_CN))
                rel_items[key] = {"a": source, "b": target, "kind": item.get("kind") or DEFAULT_KIND_CN}
                if item.get("a_to_b_addressing"):
                    rel_items[key]["a_to_b_addressing"] = item["a_to_b_addressing"]
                if item.get("b_to_a_addressing"):
                    rel_items[key]["b_to_a_addressing"] = item["b_to_a_addressing"]
                if item.get("recent_dialogues"):
                    rel_items[key]["recent_dialogues"] = item["recent_dialogues"]
                if item.get("recent_event_summaries"):
                    rel_items[key]["recent_event_summaries"] = item["recent_event_summaries"]
                if item.get("stance") is not None:
                    rel_items[key]["stance"] = item["stance"]

                fact = str(item.get("fact") or f"{source} relates_to {target}")
                if len(fact_summaries) < top_k:
                    fact_summaries.append(fact)
                if len(edges) < top_k:
                    edges.append({"source": source, "target": target, "type": "relates_to", "fact": fact, "kind": item.get("kind") or DEFAULT_KIND_CN})

        return {"nodes": [], "edges": edges, "alias_table": {}, "fact_summaries": fact_summaries, "relation_summaries": list(rel_items.values())}

    def list_relations(
        self,
        project_id: int,
        *,
        keyword: Optional[str] = None,
        kinds: Optional[List[str]] = None,
        stances: Optional[List[str]] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> Dict[str, Any]:
        group = self._group(project_id)
        cypher = (
            "MATCH (a:Entity {group_id:$group})-[r:RELATES_TO]->(b:Entity {group_id:$group}) "
            "WHERE (r.group_id = $group OR r.group_id IS NULL) "
            "RETURN a.name AS source, b.name AS target, r {.*} AS props "
            "ORDER BY coalesce(r.updated_at_epoch, 0) DESC"
        )
        rows: List[Dict[str, Any]] = []
        with self._driver.session() as sess:
            for rec in sess.run(cypher, group=group):
                item = self._parse_relation_item(rec["source"], rec["target"], rec["props"] or {})
                if _relation_matches_filters(item, keyword, kinds, stances):
                    rows.append(item)

        start = max(0, int(offset))
        end = start + max(1, int(limit))
        return {"items": rows[start:end], "total": len(rows)}

    def upsert_relation(self, project_id: int, relation: Dict[str, Any]) -> Dict[str, Any]:
        group = self._group(project_id)
        source = str(relation.get("source") or relation.get("a") or "").strip()
        target = str(relation.get("target") or relation.get("b") or "").strip()
        kind_en = str(relation.get("kind_en") or "").strip()
        if not source or not target or not kind_en:
            raise ValueError("source/target/kind_en are required")

        kind_cn = str(relation.get("kind_cn") or relation.get("kind") or EN_TO_CN_KIND.get(kind_en, kind_en) or DEFAULT_KIND_CN)
        fact = str(relation.get("fact") or f"{source} {kind_en} {target}")
        recent_dialogues = _ensure_string_list(relation.get("recent_dialogues"))
        recent_events = _ensure_event_list(relation.get("recent_event_summaries"))
        stance_value = _extract_stance_value(relation.get("stance"))
        stance_payload = _stance_to_storage(stance_value)

        cypher = (
            "MERGE (a:Entity {name: $source, group_id: $group}) "
            "MERGE (b:Entity {name: $target, group_id: $group}) "
            "MERGE (a)-[r:RELATES_TO {group_id: $group, kind_en: $kind_en}]->(b) "
            "SET r.kind = $kind_cn, r.kind_cn = $kind_cn, r.fact = $fact, "
            "r.a_to_b_addressing = $a_to_b, r.b_to_a_addressing = $b_to_a, "
            "r.recent_dialogues = $recent_dialogues, r.recent_event_summaries_json = $events_json, "
            "r.stance_json = $stance_json, r.stance_value = $stance_value, r.updated_at_epoch = $updated_at_epoch"
        )
        with self._driver.session() as sess:
            sess.run(
                cypher,
                group=group,
                source=source,
                target=target,
                kind_en=kind_en,
                kind_cn=kind_cn,
                fact=fact,
                a_to_b=relation.get("a_to_b_addressing"),
                b_to_a=relation.get("b_to_a_addressing"),
                recent_dialogues=recent_dialogues,
                events_json=json.dumps(recent_events, ensure_ascii=False),
                stance_json=json.dumps(stance_payload, ensure_ascii=False) if stance_payload is not None else None,
                stance_value=stance_value,
                updated_at_epoch=int(datetime.utcnow().timestamp() * 1000),
            )

        return _build_relation_item(
            source=source,
            target=target,
            kind_en=kind_en,
            kind_cn=kind_cn,
            fact=fact,
            a_to_b_addressing=relation.get("a_to_b_addressing"),
            b_to_a_addressing=relation.get("b_to_a_addressing"),
            recent_dialogues=recent_dialogues,
            recent_event_summaries=recent_events,
            stance=stance_value,
            updated_at=datetime.utcnow().isoformat(),
        )

    def delete_relation(self, project_id: int, source: str, target: str, kind_en: str) -> int:
        group = self._group(project_id)
        cypher = (
            "MATCH (a:Entity {group_id:$group, name:$source})-[r:RELATES_TO {group_id:$group, kind_en:$kind_en}]->"
            "(b:Entity {group_id:$group, name:$target}) WITH r DELETE r RETURN count(*) AS deleted"
        )
        with self._driver.session() as sess:
            rec = sess.run(cypher, group=group, source=source, target=target, kind_en=kind_en).single()
            return int(rec["deleted"] if rec and rec.get("deleted") is not None else 0)

    def batch_delete_relations(self, project_id: int, keys: List[Dict[str, Any]]) -> int:
        return sum(self.delete_relation(project_id, s, t, k) for s, t, k in _normalize_keys(keys))

    def batch_update_kind(self, project_id: int, keys: List[Dict[str, Any]], *, new_kind_en: str, new_kind_cn: Optional[str] = None) -> int:
        next_kind_en = str(new_kind_en or "").strip()
        if not next_kind_en:
            return 0
        next_kind_cn = str(new_kind_cn or EN_TO_CN_KIND.get(next_kind_en, next_kind_en) or DEFAULT_KIND_CN)
        updated = 0
        for source, target, old_kind_en in _normalize_keys(keys):
            item = self._get_relation(project_id, source, target, old_kind_en)
            if not item:
                continue
            item["kind_en"] = next_kind_en
            item["kind_cn"] = next_kind_cn
            item["kind"] = next_kind_cn
            item["fact"] = f"{source} {next_kind_en} {target}"
            self.upsert_relation(project_id, item)
            if old_kind_en != next_kind_en:
                self.delete_relation(project_id, source, target, old_kind_en)
            updated += 1
        return updated

    def batch_update_stance(self, project_id: int, keys: List[Dict[str, Any]], *, stance: Optional[str]) -> int:
        updated = 0
        for source, target, kind_en in _normalize_keys(keys):
            item = self._get_relation(project_id, source, target, kind_en)
            if not item:
                continue
            item["stance"] = stance
            self.upsert_relation(project_id, item)
            updated += 1
        return updated

    def batch_append_events(self, project_id: int, keys: List[Dict[str, Any]], *, events: List[Dict[str, Any]], max_size: int = 20) -> int:
        incoming = _ensure_event_list(events)
        if not incoming:
            return 0
        updated = 0
        for source, target, kind_en in _normalize_keys(keys):
            item = self._get_relation(project_id, source, target, kind_en)
            if not item:
                continue
            item["recent_event_summaries"] = _merge_events(_ensure_event_list(item.get("recent_event_summaries")), incoming, max_size=max(1, int(max_size)))
            self.upsert_relation(project_id, item)
            updated += 1
        return updated

    def delete_project_graph(self, project_id: int) -> None:
        group = self._group(project_id)
        with self._driver.session() as sess:
            sess.run("MATCH (n:Entity {group_id:$group})-[r]-() DELETE r", group=group)
            sess.run("MATCH (n:Entity {group_id:$group}) DELETE n", group=group)

class SQLModelKGProvider:
    def __init__(self, engine: Any = None) -> None:
        if engine is None:
            from app.db.session import engine as db_engine

            self._engine = db_engine
        else:
            self._engine = engine

    @staticmethod
    def _empty_result() -> Dict[str, Any]:
        return {
            "nodes": [],
            "edges": [],
            "alias_table": {},
            "fact_summaries": [],
            "relation_summaries": [],
        }

    def _relation_model_to_item(self, relation: Any) -> Dict[str, Any]:
        updated_at = relation.updated_at.isoformat() if getattr(relation, "updated_at", None) else None
        return _build_relation_item(
            source=relation.source,
            target=relation.target,
            kind_en=relation.kind_en,
            kind_cn=relation.kind_cn,
            fact=relation.fact,
            a_to_b_addressing=relation.a_to_b_addressing,
            b_to_a_addressing=relation.b_to_a_addressing,
            recent_dialogues=relation.recent_dialogues,
            recent_event_summaries=relation.recent_event_summaries,
            stance=relation.stance,
            updated_at=updated_at,
        )

    def ingest_aliases(self, project_id: int, mapping: Dict[str, List[str]]) -> None:
        return None

    def ingest_triples_with_attributes(self, project_id: int, triples: List[Tuple[str, str, str, Dict[str, Any]]]) -> None:
        for source, kind_en, target, attrs in triples or []:
            attrs = attrs or {}
            self.upsert_relation(
                project_id,
                {
                    "source": source,
                    "target": target,
                    "kind_en": kind_en,
                    "kind_cn": EN_TO_CN_KIND.get(kind_en, kind_en),
                    "fact": f"{source} {kind_en} {target}",
                    "a_to_b_addressing": attrs.get("a_to_b_addressing"),
                    "b_to_a_addressing": attrs.get("b_to_a_addressing"),
                    "recent_dialogues": attrs.get("recent_dialogues") or [],
                    "recent_event_summaries": attrs.get("recent_event_summaries") or [],
                    "stance": attrs.get("stance"),
                },
            )

    def query_subgraph(
        self,
        project_id: int,
        participants: Optional[List[str]] = None,
        radius: int = 2,
        edge_type_whitelist: Optional[List[str]] = None,
        top_k: int = 50,
        max_chapter_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        parts = [p for p in (participants or []) if isinstance(p, str) and p.strip()]
        if not parts:
            return self._empty_result()

        from app.db.models import KGRelation

        limit = max(1, int(top_k))
        fact_summaries: List[str] = []
        rel_items: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        edges: List[Dict[str, Any]] = []

        with Session(self._engine) as session:
            stmt = (
                select(KGRelation)
                .where(
                    KGRelation.project_id == project_id,
                    KGRelation.source.in_(parts),
                    KGRelation.target.in_(parts),
                )
                .order_by(KGRelation.updated_at.desc(), KGRelation.id.desc())
                .limit(limit)
            )
            relations = session.exec(stmt).all()

            for relation in relations:
                item = self._relation_model_to_item(relation)
                key = (relation.source, relation.target, str(item.get("kind") or DEFAULT_KIND_CN))
                rel_items[key] = {"a": relation.source, "b": relation.target, "kind": item.get("kind") or DEFAULT_KIND_CN}
                if item.get("a_to_b_addressing"):
                    rel_items[key]["a_to_b_addressing"] = item["a_to_b_addressing"]
                if item.get("b_to_a_addressing"):
                    rel_items[key]["b_to_a_addressing"] = item["b_to_a_addressing"]
                if item.get("recent_dialogues"):
                    rel_items[key]["recent_dialogues"] = item["recent_dialogues"]
                if item.get("recent_event_summaries"):
                    rel_items[key]["recent_event_summaries"] = item["recent_event_summaries"]
                if item.get("stance") is not None:
                    rel_items[key]["stance"] = item["stance"]

                fact = str(item.get("fact") or f"{relation.source} relates_to {relation.target}")
                if len(fact_summaries) < limit:
                    fact_summaries.append(fact)
                if len(edges) < limit:
                    edges.append({"source": relation.source, "target": relation.target, "type": "relates_to", "fact": fact, "kind": item.get("kind") or DEFAULT_KIND_CN})

        return {"nodes": [], "edges": edges, "alias_table": {}, "fact_summaries": fact_summaries, "relation_summaries": list(rel_items.values())}

    def list_relations(
        self,
        project_id: int,
        *,
        keyword: Optional[str] = None,
        kinds: Optional[List[str]] = None,
        stances: Optional[List[str]] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> Dict[str, Any]:
        from app.db.models import KGRelation

        with Session(self._engine) as session:
            stmt = select(KGRelation).where(KGRelation.project_id == project_id).order_by(KGRelation.updated_at.desc(), KGRelation.id.desc())
            rows = session.exec(stmt).all()

        items = [self._relation_model_to_item(row) for row in rows]
        filtered = [item for item in items if _relation_matches_filters(item, keyword, kinds, stances)]
        start = max(0, int(offset))
        end = start + max(1, int(limit))
        return {"items": filtered[start:end], "total": len(filtered)}

    def upsert_relation(self, project_id: int, relation: Dict[str, Any]) -> Dict[str, Any]:
        from app.db.models import KGRelation

        source = str(relation.get("source") or relation.get("a") or "").strip()
        target = str(relation.get("target") or relation.get("b") or "").strip()
        kind_en = str(relation.get("kind_en") or "").strip()
        if not source or not target or not kind_en:
            raise ValueError("source/target/kind_en are required")

        kind_cn = str(relation.get("kind_cn") or relation.get("kind") or EN_TO_CN_KIND.get(kind_en, kind_en) or DEFAULT_KIND_CN)
        now = datetime.now()

        with Session(self._engine) as session:
            stmt = select(KGRelation).where(
                KGRelation.project_id == project_id,
                KGRelation.source == source,
                KGRelation.target == target,
                KGRelation.kind_en == kind_en,
            )
            model = session.exec(stmt).first()
            if model is None:
                model = KGRelation(project_id=project_id, source=source, target=target, kind_en=kind_en, created_at=now)

            model.kind_cn = kind_cn
            model.fact = str(relation.get("fact") or f"{source} {kind_en} {target}")
            model.a_to_b_addressing = relation.get("a_to_b_addressing")
            model.b_to_a_addressing = relation.get("b_to_a_addressing")
            model.recent_dialogues = _ensure_string_list(relation.get("recent_dialogues"))
            model.recent_event_summaries = _ensure_event_list(relation.get("recent_event_summaries"))
            model.stance = _stance_to_storage(relation.get("stance"))
            model.updated_at = now

            session.add(model)
            session.commit()
            session.refresh(model)
            return self._relation_model_to_item(model)

    def delete_relation(self, project_id: int, source: str, target: str, kind_en: str) -> int:
        from app.db.models import KGRelation

        with Session(self._engine) as session:
            result = session.exec(
                delete(KGRelation).where(
                    KGRelation.project_id == project_id,
                    KGRelation.source == source,
                    KGRelation.target == target,
                    KGRelation.kind_en == kind_en,
                )
            )
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)

    def batch_delete_relations(self, project_id: int, keys: List[Dict[str, Any]]) -> int:
        from app.db.models import KGRelation

        deleted_total = 0
        with Session(self._engine) as session:
            for source, target, kind_en in _normalize_keys(keys):
                result = session.exec(
                    delete(KGRelation).where(
                        KGRelation.project_id == project_id,
                        KGRelation.source == source,
                        KGRelation.target == target,
                        KGRelation.kind_en == kind_en,
                    )
                )
                deleted_total += int(getattr(result, "rowcount", 0) or 0)
            session.commit()

        return deleted_total

    def batch_update_kind(self, project_id: int, keys: List[Dict[str, Any]], *, new_kind_en: str, new_kind_cn: Optional[str] = None) -> int:
        from app.db.models import KGRelation

        next_kind_en = str(new_kind_en or "").strip()
        if not next_kind_en:
            return 0
        next_kind_cn = str(new_kind_cn or EN_TO_CN_KIND.get(next_kind_en, next_kind_en) or DEFAULT_KIND_CN)

        updated = 0
        now = datetime.now()
        with Session(self._engine) as session:
            for source, target, old_kind_en in _normalize_keys(keys):
                old_stmt = select(KGRelation).where(
                    KGRelation.project_id == project_id,
                    KGRelation.source == source,
                    KGRelation.target == target,
                    KGRelation.kind_en == old_kind_en,
                )
                old_relation = session.exec(old_stmt).first()
                if old_relation is None:
                    continue

                if old_kind_en == next_kind_en:
                    old_relation.kind_cn = next_kind_cn
                    old_relation.fact = f"{source} {next_kind_en} {target}"
                    old_relation.updated_at = now
                    session.add(old_relation)
                    updated += 1
                    continue

                conflict_stmt = select(KGRelation).where(
                    KGRelation.project_id == project_id,
                    KGRelation.source == source,
                    KGRelation.target == target,
                    KGRelation.kind_en == next_kind_en,
                )
                conflict = session.exec(conflict_stmt).first()

                target_relation = conflict or old_relation
                target_relation.kind_en = next_kind_en
                target_relation.kind_cn = next_kind_cn
                target_relation.fact = f"{source} {next_kind_en} {target}"
                target_relation.a_to_b_addressing = old_relation.a_to_b_addressing
                target_relation.b_to_a_addressing = old_relation.b_to_a_addressing
                target_relation.recent_dialogues = _ensure_string_list(old_relation.recent_dialogues)
                target_relation.recent_event_summaries = _ensure_event_list(old_relation.recent_event_summaries)
                target_relation.stance = old_relation.stance
                target_relation.updated_at = now
                session.add(target_relation)

                if conflict is not None:
                    session.delete(old_relation)
                updated += 1

            session.commit()

        return updated

    def batch_update_stance(self, project_id: int, keys: List[Dict[str, Any]], *, stance: Optional[str]) -> int:
        from app.db.models import KGRelation

        updated = 0
        now = datetime.now()
        stance_payload = _stance_to_storage(stance)
        with Session(self._engine) as session:
            for source, target, kind_en in _normalize_keys(keys):
                stmt = select(KGRelation).where(
                    KGRelation.project_id == project_id,
                    KGRelation.source == source,
                    KGRelation.target == target,
                    KGRelation.kind_en == kind_en,
                )
                relation = session.exec(stmt).first()
                if relation is None:
                    continue
                relation.stance = stance_payload
                relation.updated_at = now
                session.add(relation)
                updated += 1
            session.commit()

        return updated

    def batch_append_events(self, project_id: int, keys: List[Dict[str, Any]], *, events: List[Dict[str, Any]], max_size: int = 20) -> int:
        from app.db.models import KGRelation

        incoming = _ensure_event_list(events)
        if not incoming:
            return 0

        updated = 0
        now = datetime.now()
        with Session(self._engine) as session:
            for source, target, kind_en in _normalize_keys(keys):
                stmt = select(KGRelation).where(
                    KGRelation.project_id == project_id,
                    KGRelation.source == source,
                    KGRelation.target == target,
                    KGRelation.kind_en == kind_en,
                )
                relation = session.exec(stmt).first()
                if relation is None:
                    continue

                relation.recent_event_summaries = _merge_events(_ensure_event_list(relation.recent_event_summaries), incoming, max_size=max(1, int(max_size)))
                relation.updated_at = now
                session.add(relation)
                updated += 1

            session.commit()

        return updated

    def delete_project_graph(self, project_id: int) -> None:
        from app.db.models import KGRelation

        with Session(self._engine) as session:
            session.exec(delete(KGRelation).where(KGRelation.project_id == project_id))
            session.commit()


def get_provider(engine: Any = None) -> KnowledgeGraphProvider:
    from app.core.config import settings

    provider_name = (settings.kg.provider or "sqlmodel").strip().lower()
    if provider_name in {"sqlmodel", "sqlite"}:
        return SQLModelKGProvider(engine=engine)

    if provider_name == "neo4j":
        return Neo4jKGProvider()

    raise KnowledgeGraphUnavailableError(f"Unsupported knowledge graph provider: {settings.kg.provider}")
