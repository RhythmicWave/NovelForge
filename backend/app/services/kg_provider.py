from __future__ import annotations

import os
import json
from typing import Any, Dict, List, Optional, Tuple, Protocol

from dotenv import load_dotenv

# 优先加载 backend/.env，其次加载默认 .env
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
_env_path = os.path.join(_BACKEND_DIR, '.env')
try:
    load_dotenv(_env_path, override=False)
    load_dotenv(override=False)
except Exception:
    pass

# 统一从 schema 导入中英映射，避免重复定义
from app.schemas.relation_extract import EN_TO_CN_KIND


class KnowledgeGraphUnavailableError(RuntimeError):
    pass


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


# === Graphiti 实现（包装现有 GraphitiClient） ===
class GraphitiKGProvider:
    def __init__(self) -> None:
        from app.services.graphiti_client import GraphitiClient  # 延迟导入，避免强耦合
        self._client = GraphitiClient()

    def ingest_aliases(self, project_id: int, mapping: Dict[str, List[str]]) -> None:
        self._client.ingest_aliases(project_id, mapping)

    def ingest_triples_with_attributes(self, project_id: int, triples: List[Tuple[str, str, str, Dict[str, Any]]]) -> None:
        self._client.ingest_triples_with_attributes(project_id, triples)

    def query_subgraph(
        self,
        project_id: int,
        participants: Optional[List[str]] = None,
        radius: int = 2,
        edge_type_whitelist: Optional[List[str]] = None,
        top_k: int = 50,
        max_chapter_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        return self._client.query_subgraph(project_id, participants, radius, edge_type_whitelist, top_k, max_chapter_id)


# === Neo4j 官方驱动实现 ===
class Neo4jKGProvider:
    """用 Neo4j 官方驱动复现最小能力（命名空间隔离、别名与关系写入、子图检索）。"""
    def __init__(self) -> None:
        from neo4j import GraphDatabase  # type: ignore
        uri = os.getenv("NEO4J_URI") or os.getenv("GRAPH_DB_URI") or "bolt://127.0.0.1:7687"
        user = os.getenv("NEO4J_USER") or os.getenv("GRAPH_DB_USER") or "neo4j"
        password = os.getenv("NEO4J_PASSWORD") or os.getenv("GRAPH_DB_PASSWORD") or "neo4j"
        self._driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self) -> None:
        try:
            self._driver.close()
        except Exception:
            pass

    @staticmethod
    def _group(project_id: int) -> str:
        return f"proj:{project_id}"

    def ingest_aliases(self, project_id: int, mapping: Dict[str, List[str]]) -> None:
        group = self._group(project_id)
        if not mapping:
            return
        cypher = (
            "UNWIND $rows AS row "
            "MERGE (a:Entity {name: row.s, group_id: $group}) "
            "MERGE (b:Alias {name: row.o, group_id: $group}) "
            "MERGE (a)-[r:HAS_ALIAS]->(b) "
            "SET r.fact = row.fact"
        )
        rows = [{"s": s, "o": alias, "fact": f"{s} has_alias {alias}"} for s, aliases in mapping.items() for alias in (aliases or [])]
        if not rows:
            return
        with self._driver.session() as sess:
            sess.run(cypher, rows=rows, group=group)

    def ingest_triples_with_attributes(self, project_id: int, triples: List[Tuple[str, str, str, Dict[str, Any]]]) -> None:
        group = self._group(project_id)
        if not triples:
            return
        # 关系类型统一为 :RELATES_TO，具体类型存入 kind 属性
        rows: List[Dict[str, Any]] = []
        for s, p, o, attrs in triples:
            # 只有别名关系保持独立类型
            if p == "has_alias":
                continue
            
            payload: Dict[str, Any] = {
                "s": s,
                "o": o,
                "kind": p,  # 'ally', 'enemy' 等存入属性
                "fact": f"{s} {p} {o}",
                "a_to_b": attrs.get("a_to_b_addressing"),
                "b_to_a": attrs.get("b_to_a_addressing"),
                "recent_dialogues": attrs.get("recent_dialogues") or [],
                "recent_event_summaries_json": json.dumps(attrs.get("recent_event_summaries") or [], ensure_ascii=False),
                "stance_json": json.dumps(getattr(attrs.get("stance"), "model_dump", lambda: attrs.get("stance"))(), ensure_ascii=False) if attrs.get("stance") is not None else None,
            }
            rows.append(payload)
        
        # 别名写入（独立类型）
        alias_triples = [(s,p,o) for s,p,o,_ in triples if p == "has_alias"]
        if alias_triples:
            alias_rows = [{"s": s, "o": o, "fact": f"{s} {p} {o}"} for s, p, o in alias_triples]
            alias_cypher = (
                "UNWIND $rows AS row "
                "MERGE (a:Entity {name: row.s, group_id: $group}) "
                "MERGE (b:Entity {name: row.o, group_id: $group}) "  # 别名也作为 Entity 节点，便于双向查询
                "MERGE (a)-[r:HAS_ALIAS]->(b) "
                "SET r.fact = row.fact"
            )
            with self._driver.session() as sess:
                sess.run(alias_cypher, rows=alias_rows, group=group)

        # 其他关系写入 :RELATES_TO
        if not rows: return
        cypher = (
            "UNWIND $rows AS row "
            "MERGE (a:Entity {name: row.s, group_id: $group}) "
            "MERGE (b:Entity {name: row.o, group_id: $group}) "
            "MERGE (a)-[r:RELATES_TO]->(b) "
            "SET r.kind = row.kind, "
            "r.fact = row.fact, "
            "r.a_to_b_addressing = row.a_to_b, "
            "r.b_to_a_addressing = row.b_to_a, "
            "r.recent_dialogues = row.recent_dialogues, "
            "r.recent_event_summaries_json = row.recent_event_summaries_json, "
            "r.stance_json = row.stance_json"
        )
        with self._driver.session() as sess:
            sess.run(cypher, rows=rows, group=group)

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
        # 查询时匹配 :HAS_ALIAS 和 :RELATES_TO
        cypher = (
            "MATCH (a:Entity {group_id:$group})-[r]->(b:Entity {group_id:$group}) "
            "WHERE a.name IN $parts OR b.name IN $parts "
            "RETURN a.name AS a, type(r) AS t, b.name AS b, r {.*} as props "
            "LIMIT $limit"
        )
        alias_table: Dict[str, List[str]] = {}
        fact_summaries: List[str] = []
        rel_items: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        edges: List[Dict[str, Any]] = []
        with self._driver.session() as sess:
            results = sess.run(cypher, group=group, parts=parts, limit=max(1, int(top_k)))
            for rec in results:
                a = rec["a"]; b = rec["b"]; t = rec["t"]; props = rec["props"] or {}
                fact = props.get("fact") or f"{a} {props.get('kind', t)} {b}"

                if t == "HAS_ALIAS":
                    alias_table.setdefault(a, []).append(b)
                elif t == "RELATES_TO":
                    pred_en = props.get("kind")
                    if not pred_en: continue
                    kind_cn = EN_TO_CN_KIND.get(pred_en, "同盟")
                    key = (a, b, pred_en)
                    if key not in rel_items:
                        rel_items[key] = { "a": a, "b": b, "kind": kind_cn }
                    # 解析属性
                    try:
                        ev = json.loads(props.get("recent_event_summaries_json") or "[]")
                    except Exception: ev = []
                    try:
                        s = json.loads(props.get("stance_json") or "null")
                    except Exception: s = None
                    if props.get("a_to_b_addressing"): rel_items[key]["a_to_b_addressing"] = props.get("a_to_b_addressing")
                    if props.get("b_to_a_addressing"): rel_items[key]["b_to_a_addressing"] = props.get("b_to_a_addressing")
                    if props.get("recent_dialogues"): rel_items[key]["recent_dialogues"] = props.get("recent_dialogues")
                    if ev: rel_items[key]["recent_event_summaries"] = ev
                    if s is not None: rel_items[key]["stance"] = s
                # edges/facts 回显
                if len(fact_summaries) < top_k:
                    fact_summaries.append(fact)
                if len(edges) < top_k:
                    edges.append({"source": a, "target": b, "type": props.get('kind', t).lower(), "fact": fact})
        relation_summaries = list(rel_items.values())
        return {
            "nodes": [],
            "edges": edges,
            "alias_table": alias_table,
            "fact_summaries": fact_summaries,
            "relation_summaries": relation_summaries,
        }


def get_provider() -> KnowledgeGraphProvider:
    # 优先新变量；兼容旧 USE_GRAPHITI
    provider_name = os.getenv("KNOWLEDGE_GRAPH_PROVIDER")
    if not provider_name:
        use_graphiti = os.getenv("USE_GRAPHITI", "false").lower() == "true"
        provider_name = "graphiti" if use_graphiti else "neo4j"
    name = provider_name.strip().lower()
    if name == "graphiti":
        return GraphitiKGProvider()
    elif name == "neo4j":
        return Neo4jKGProvider()
    else:
        raise KnowledgeGraphUnavailableError(f"未知的知识图谱提供方: {provider_name}") 