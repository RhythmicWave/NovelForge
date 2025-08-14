from __future__ import annotations

import os
import asyncio
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

# 优先从 .env 加载（项目根/后端根均可），随后环境变量可覆盖
load_dotenv()

# 是否启用 Graphiti（默认开启）。可通过 USE_GRAPHITI=false 关闭。
USE_GRAPHITI_DEFAULT = os.getenv("USE_GRAPHITI", "true").lower() == "true"

from graphiti_core import Graphiti  # type: ignore

from datetime import datetime, timezone, timedelta

# 引入统一的关系摘要模型（避免本文件重复定义）
from app.schemas.relation_extract import RelationItem, RecentEventSummary

# 英文谓词 → 中文关系 类型映射（用于 RelationItem.kind）
EN_TO_CN_KIND: Dict[str, str] = {
    "ally": "同盟",
    "enemy": "敌对",
    "family": "亲属",
    "mentor": "师徒",
    "rival": "对手",
    "member_of": "隶属",
}

# 合成时间轴基准（用于用 chapter_id 映射到 reference_time）
SYNTHETIC_TIME_BASE = datetime(2000, 1, 1, tzinfo=timezone.utc)


class GraphitiUnavailableError(RuntimeError):
    pass


class GraphitiClient:
    def __init__(self) -> None:
        self._graph: Optional[Graphiti] = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._initialized: bool = False
        self._enabled: bool = USE_GRAPHITI_DEFAULT
        # 可调的超时（秒）
        self._timeout_seconds: float = float(os.getenv("GRAPHITI_TIMEOUT_SECONDS", "60"))

    # --- 内部：获取事件循环 ---
    def _loop_get(self) -> asyncio.AbstractEventLoop:
        if self._loop and self._loop.is_running():
            return self._loop
        try:
            self._loop = asyncio.get_event_loop()
        except RuntimeError:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
        return self._loop

    # 小工具：带超时运行异步任务
    def _run(self, coro) -> Any:
        loop = self._loop_get()
        try:
            return loop.run_until_complete(asyncio.wait_for(coro, timeout=self._timeout_seconds))
        except asyncio.TimeoutError as te:
            raise GraphitiUnavailableError(f"Graphiti 调用超时（>{self._timeout_seconds}s），请检查网络/LLM配置或增大 GRAPHITI_TIMEOUT_SECONDS") from te

    # --- 读取连接参数（兼容 NEO4J_* 与 GRAPH_DB_* 环境变量名） ---
    def _get_conn(self) -> Tuple[str, str, str]:
        uri = os.getenv("NEO4J_URI") or os.getenv("GRAPH_DB_URI") or "bolt://localhost:7687"
        # 规范化 localhost 以避免 IPv6 (::1) 解析导致的连接问题
        uri = uri.replace("localhost", "127.0.0.1")
        user = os.getenv("NEO4J_USER") or os.getenv("GRAPH_DB_USER") or "neo4j"
        password = os.getenv("NEO4J_PASSWORD") or os.getenv("GRAPH_DB_PASSWORD") or "neo4j"
        if os.getenv("GRAPHITI_TELEMETRY_ENABLED") is None:
            os.environ["GRAPHITI_TELEMETRY_ENABLED"] = "false"
        return uri, user, password

    # --- 读取 LLM 配置并构建可选客户端 ---
    def _get_llm_clients(self) -> Dict[str, Any]:
        """
        基于环境变量返回 Graphiti 的 llm/embedder/cross_encoder 可选参数。
        根据新方案，此函数已禁用，因为LLM调用由 agent_service 统一处理。
        返回空字典以避免初始化不必要的客户端。
        """
        
        return {"api_key":""}

    async def _ainit(self) -> None:
        if self._initialized:
            return
        if not self._enabled:
            self._initialized = True
            return
        uri, user, pwd = self._get_conn()
        try:
            # 构建可选的 LLM/Embedder 配置
            llm_kwargs = self._get_llm_clients()
            self._graph = Graphiti(uri, user, pwd, **llm_kwargs)
            # 首次建立索引/约束（幂等）
            await asyncio.wait_for(self._graph.build_indices_and_constraints(), timeout=self._timeout_seconds)
            self._initialized = True
        except Exception as e:
            raise GraphitiUnavailableError(f"Graphiti 初始化失败：{e}")

    def _ensure_ready(self) -> None:
        # 已初始化时直接返回，避免重复进入事件循环
        if self._initialized:
            return
        self._run(self._ainit())

    # --- 对外：摄取别名映射为三元组（entity -has_alias-> alias） ---
    def ingest_aliases(self, project_id: int, mapping: Dict[str, List[str]]) -> None:
        self._ensure_ready()
        if not self._enabled or not mapping:
            return
        triples: List[Tuple[str, str, str]] = []
        for entity, aliases in (mapping or {}).items():
            for al in aliases:
                triples.append((entity, "has_alias", al))
        if not triples:
            return
        try:
            self._run(self._add_fact_triples_compat(project_id, triples))
        except Exception as e:
            raise GraphitiUnavailableError(f"写入别名三元组失败：{e}")

    # --- 对外：摄取事实三元组 ---
    def ingest_triples(self, project_id: int, triples: List[Tuple[str, str, str]]) -> None:
        self._ensure_ready()
        if not self._enabled:
            return
        if not triples:
            return
        try:
            # 兼容旧的、无属性的写入
            triples_with_attrs = [(s, p, o, {}) for s, p, o in triples]
            self._run(self._add_fact_triples_with_attributes_compat(project_id, triples_with_attrs))
        except Exception as e:
            raise GraphitiUnavailableError(f"写入事实三元组失败：{e}")

    def ingest_triples_with_attributes(self, project_id: int, triples: List[Tuple[str, str, str, Dict[str, Any]]]) -> None:
        self._ensure_ready()
        if not self._enabled:
            return
        if not triples:
            return
        try:
            self._run(self._add_fact_triples_with_attributes_compat(project_id, triples))
        except Exception as e:
            raise GraphitiUnavailableError(f"写入带属性的三元组失败：{e}")

    # --- 对外：添加原文/结构化 Episode（如需） ---

    # --- 对外：按参与者做混合检索并返回简易子图 + 结构化摘要 ---
    def query_subgraph(
        self,
        project_id: int,
        participants: Optional[List[str]] = None,
        radius: int = 2,
        edge_type_whitelist: Optional[List[str]] = None,
        top_k: int = 50,
        max_chapter_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        self._ensure_ready()
        if not self._enabled:
            return {"nodes": [], "edges": [], "alias_table": {}, "fact_summaries": [], "relation_summaries": []}
        parts = [p for p in (participants or []) if isinstance(p, str) and p.strip()]
        query_all = " ".join(parts)
        nodes: Dict[str, Dict[str, Any]] = {}
        edges: List[Dict[str, Any]] = []
        allowed_group = f"proj:{project_id}"
        boundary_time = None  # 简化：当前不按章节时间裁剪

        try:
            # 简化：仅执行一次 search，无需 rerank
            results = self._run(self._search(query_all)) if query_all else []
        except Exception as e:
            raise GraphitiUnavailableError(f"Graphiti 查询失败：{e}")

        alias_table: Dict[str, List[str]] = {}
        fact_summaries: List[str] = []
        relation_summaries_map: Dict[Tuple[str, str, str], RelationItem] = {}
        allowed_relation_kinds = {"ally", "enemy", "family", "mentor", "rival", "member_of"}

        for r in results:
            try:
                grp = getattr(r, "group_id", None)
                if grp and str(grp) != allowed_group:
                    continue
                if boundary_time is not None:
                    valid_at = getattr(r, "valid_at", None)
                    if valid_at and isinstance(valid_at, datetime) and valid_at > boundary_time:
                        continue
                # 边/关系的处理
                if hasattr(r, 'source_node_uuid') and hasattr(r, 'target_node_uuid'):
                    edge = r
                    subj = getattr(edge, 'source_node_name', '')
                    obj = getattr(edge, 'target_node_name', '')
                    pred = getattr(edge, 'name', '')
                    
                    if pred == "has_alias":
                        alias_table.setdefault(subj, []).append(obj)
                    elif pred in allowed_relation_kinds:
                        cn_kind = EN_TO_CN_KIND.get(pred, "同盟")
                        key = (subj, obj, pred)
                        entry = relation_summaries_map.get(key)
                        if not entry:
                            # 从 attributes 恢复 RelationItem
                            attrs = getattr(edge, 'attributes', {})
                            # 确保 recent_event_summaries 是正确的模型列表
                            if 'recent_event_summaries' in attrs and isinstance(attrs['recent_event_summaries'], list):
                                attrs['recent_event_summaries'] = [
                                    RecentEventSummary(**s) if isinstance(s, dict) else s 
                                    for s in attrs['recent_event_summaries']
                                ]
                            entry = RelationItem(a=subj, b=obj, kind=cn_kind, **attrs)
                            relation_summaries_map[key] = entry
                    
                    fact = getattr(edge, "fact", f"{subj} {pred} {obj}")
                    if len(fact_summaries) < max(1, top_k):
                        fact_summaries.append(fact)
                    if len(edges) < max(1, top_k):
                        edges.append({"source": subj, "target": obj, "type": pred, "fact": fact})
                # 节点/事实的处理（作为兜底）
                else:
                    fact = getattr(r, "fact", None) or ""
                    uuid = getattr(r, "uuid", None) or getattr(r, "source_node_uuid", None) or None
                    if uuid and uuid not in nodes:
                        nodes[uuid] = {"id": uuid, "label": (fact[:80] + "...") if len(fact) > 80 else fact, "type": "fact"}

            except Exception:
                pass
        
        relation_summaries = [m.model_dump() for m in relation_summaries_map.values()]
        return {
            "nodes": list(nodes.values()),
            "edges": edges,
            "alias_table": alias_table,
            "fact_summaries": fact_summaries,
            "relation_summaries": relation_summaries,
        }

    # --- Async 实现细节 ---

    async def _add_fact_triples_compat(self, project_id: int, triples: List[Tuple[str, str, str]]) -> None:
        """
        Graphiti v3 兼容写入三元组：
        - 逐条调用 add_triplet(EntityNode, EntityEdge, EntityNode)
        """
        assert self._graph is not None

        from graphiti_core.nodes import EntityNode  # type: ignore
        from graphiti_core.edges import EntityEdge  # type: ignore
        import uuid as _uuid
        from datetime import datetime, timezone
        group_id = f"proj:{project_id}"
        for s, p, o in triples:
            # 基于名称创建节点；Graphiti 会做去重
            s_uuid = str(_uuid.uuid4())
            o_uuid = str(_uuid.uuid4())
            source = EntityNode(uuid=s_uuid, name=str(s), group_id=group_id)
            target = EntityNode(uuid=o_uuid, name=str(o), group_id=group_id)
            edge = EntityEdge(
                group_id=group_id,
                source_node_uuid=s_uuid,
                target_node_uuid=o_uuid,
                created_at=datetime.now(timezone.utc),
                name=str(p),
                fact=f"{s} {p} {o}",
            )
            await self._graph.add_triplet(source, edge, target)

    async def _add_fact_triples_with_attributes_compat(self, project_id: int, triples: List[Tuple[str, str, str, Dict[str, Any]]]) -> None:
        """
        Graphiti v3 兼容写入三元组（带属性）：
        - 逐条调用 add_triplet(EntityNode, EntityEdge, EntityNode)
        - edge.attributes 携带详细信息
        """
        assert self._graph is not None

        from graphiti_core.nodes import EntityNode  # type: ignore
        from graphiti_core.edges import EntityEdge  # type: ignore
        import uuid as _uuid
        from datetime import datetime, timezone
        group_id = f"proj:{project_id}"

        for s, p, o, attrs in triples:
            s_uuid = str(_uuid.uuid4())
            o_uuid = str(_uuid.uuid4())
            source = EntityNode(uuid=s_uuid, name=str(s), group_id=group_id)
            target = EntityNode(uuid=o_uuid, name=str(o), group_id=group_id)

            # 序列化 stance（如果存在）
            if 'stance' in attrs and hasattr(attrs['stance'], 'model_dump'):
                attrs['stance'] = attrs['stance'].model_dump()
            
            # 确保事件摘要是字典列表
            if 'recent_event_summaries' in attrs and isinstance(attrs['recent_event_summaries'], list):
                 attrs['recent_event_summaries'] = [
                    s.model_dump() if hasattr(s, 'model_dump') else s
                    for s in attrs['recent_event_summaries']
                ]

            edge = EntityEdge(
                group_id=group_id,
                source_node_uuid=s_uuid,
                target_node_uuid=o_uuid,
                created_at=datetime.now(timezone.utc),
                name=str(p),
                fact=f"{s} {p} {o}",
                attributes=attrs or {},
            )
            await self._graph.add_triplet(source, edge, target)

    async def _search(self, query: str, center_node_uuid: Optional[str] = None):
        assert self._graph is not None
        if not query:
            return []
        # 查询只返回当前命名空间内的结果；Graphiti v3 的搜索接口返回已带 group_id 的条目
        results = await self._graph.search(query, center_node_uuid=center_node_uuid)
        # 这里不过滤，统一在对外 query_subgraph() 处做按项目的严格过滤
        return results 