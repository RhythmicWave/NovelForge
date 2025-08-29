from __future__ import annotations

import os
import json
from typing import Any, Dict, List, Optional, Tuple, Protocol


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
	def delete_project_graph(self, project_id: int) -> None: ...


class Neo4jKGProvider:
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

	def ingest_triples_with_attributes(self, project_id: int, triples: List[Tuple[str, str, str, Dict[str, Any]]]) -> None:
		group = self._group(project_id)
		if not triples:
			return
		rows: List[Dict[str, Any]] = []
		for s, p, o, attrs in triples:
			# 只写 RELATES_TO，具体类型写入 kind(kind_cn/kind_en)
			kind_cn = EN_TO_CN_KIND.get(p, p)
			payload: Dict[str, Any] = {
				"s": s,
				"o": o,
				"kind_cn": kind_cn,
				"kind_en": p,
				"fact": f"{s} {p} {o}",
				"a_to_b": attrs.get("a_to_b_addressing"),
				"b_to_a": attrs.get("b_to_a_addressing"),
				"recent_dialogues": attrs.get("recent_dialogues") or [],
				"recent_event_summaries_json": json.dumps(attrs.get("recent_event_summaries") or [], ensure_ascii=False),
				"stance_json": json.dumps(getattr(attrs.get("stance"), "model_dump", lambda: attrs.get("stance"))(), ensure_ascii=False) if attrs.get("stance") is not None else None,
			}
			rows.append(payload)

		if not rows:
			return
		cypher = (
			"UNWIND $rows AS row "
			"MERGE (a:Entity {name: row.s, group_id: $group}) "
			"MERGE (b:Entity {name: row.o, group_id: $group}) "
			"MERGE (a)-[r:RELATES_TO]->(b) "
			"SET r.kind = row.kind_cn, "
			"r.kind_en = row.kind_en, "
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

		# 仅查询 RELATES_TO
		rel_cypher = (
			"MATCH (a:Entity {group_id:$group})-[r:RELATES_TO]->(b:Entity {group_id:$group}) "
			"WHERE a.name IN $parts AND b.name IN $parts "
			"RETURN a.name AS a, 'RELATES_TO' AS t, b.name AS b, r {.*} as props "
			"LIMIT $limit"
		)

		fact_summaries: List[str] = []
		rel_items: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
		edges: List[Dict[str, Any]] = []
		with self._driver.session() as sess:
			results = sess.run(rel_cypher, group=group, parts=parts, limit=max(1, int(top_k)))
			for rec in results:
				a = rec["a"]; b = rec["b"]; t = rec["t"]; props = rec["props"] or {}
				# 中文关系类型优先来自属性
				kind_cn = props.get("kind") or props.get("kind_cn") or None
				if not kind_cn and props.get("kind_en"):
					kind_cn = EN_TO_CN_KIND.get(props.get("kind_en"), props.get("kind_en"))
				if not kind_cn:
					kind_cn = "其他"
				fact = props.get("fact") or f"{a} relates_to {b}"
				key = (a, b, str(kind_cn))
				if key not in rel_items:
					rel_items[key] = { "a": a, "b": b, "kind": kind_cn }
				# 附带属性
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
				# 回显
				if len(fact_summaries) < top_k:
					fact_summaries.append(fact)
				if len(edges) < top_k:
					edges.append({"source": a, "target": b, "type": "relates_to", "fact": fact, "kind": kind_cn})

		relation_summaries = list(rel_items.values())
		return {
			"nodes": [],
			"edges": edges,
			"alias_table": {},
			"fact_summaries": fact_summaries,
			"relation_summaries": relation_summaries,
		}

	def delete_project_graph(self, project_id: int) -> None:
		"""删除某个项目(group_id)下的所有节点和关系。"""
		group = self._group(project_id)
		with self._driver.session() as sess:
			# 先删关系再删节点
			sess.run("MATCH (n:Entity {group_id:$group})-[r]-() DELETE r", group=group)
			sess.run("MATCH (n:Entity {group_id:$group}) DELETE n", group=group)


def get_provider() -> KnowledgeGraphProvider:
	# 仅使用 Neo4j 提供方
	return Neo4jKGProvider() 