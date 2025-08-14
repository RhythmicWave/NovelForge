from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol
from sqlmodel import Session

from app.services.memory_service import MemoryService
from app.services.kg_provider import get_provider


class ConsistencyProvider(Protocol):
    """
    一致性提供方抽象：负责根据参与者与时间边界返回结构化事实子图（用于注入一致性快照）。
    返回结构需包含：alias_table: Dict[str, List[str]] 与 fact_summaries: List[str]
    """

    def get_facts_structured(
        self,
        project_id: int,
        participants: Optional[List[str]] = None,
        radius: int = 2,
        edge_type_whitelist: Optional[List[str]] = None,
        top_k: int = 50,
        max_chapter_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        ...


class MemoryConsistencyProvider:
    """
    基于现有 MemoryService 的一致性提供方实现。
    如 MemoryService 底层已接可切换 KG Provider，则保持透明。
    """

    def __init__(self, session: Session) -> None:
        self._session = session
        self._svc = MemoryService(session)

    def get_facts_structured(
        self,
        project_id: int,
        participants: Optional[List[str]] = None,
        radius: int = 2,
        edge_type_whitelist: Optional[List[str]] = None,
        top_k: int = 50,
        max_chapter_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        sub = self._svc.query_subgraph(
            project_id=project_id,
            participants=participants,
            radius=radius,
            edge_type_whitelist=edge_type_whitelist,
            top_k=top_k,
            max_chapter_id=max_chapter_id,
        )
        # 仅暴露必要字段，保持 context_service 兼容
        return {
            "alias_table": sub.get("alias_table") or {},
            "fact_summaries": sub.get("fact_summaries") or [],
            "relation_summaries": sub.get("relation_summaries") or [],
            # 额外传回原始子图（可选）
            "_raw": sub,
        }


class DirectKGConsistencyProvider:
    """
    直接使用底层可切换 KG Provider 的一致性提供方实现。
    """

    def __init__(self) -> None:
        self._client = get_provider()

    def get_facts_structured(
        self,
        project_id: int,
        participants: Optional[List[str]] = None,
        radius: int = 2,
        edge_type_whitelist: Optional[List[str]] = None,
        top_k: int = 50,
        max_chapter_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        sub = self._client.query_subgraph(
            project_id=project_id,
            participants=participants,
            radius=radius,
            edge_type_whitelist=edge_type_whitelist,
            top_k=top_k,
            max_chapter_id=max_chapter_id,
        )
        return {
            "alias_table": sub.get("alias_table") or {},
            "fact_summaries": sub.get("fact_summaries") or [],
            "relation_summaries": sub.get("relation_summaries") or [],
            "_raw": sub,
        } 