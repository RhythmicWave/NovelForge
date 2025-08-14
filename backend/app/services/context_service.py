from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from sqlmodel import Session, select

from app.db.models import Card, CardType
from app.services.memory_service import MemoryService
from app.services.consistency_provider import MemoryConsistencyProvider, DirectKGConsistencyProvider, ConsistencyProvider
from app.schemas.context import FactsStructured

# === 可热更新设置 ===
@dataclass
class ContextSettings:
    recent_chapters_window: int
    total_context_budget_chars: int
    soft_budget_chars: int
    quota_recent: int
    quota_older_summary: int
    quota_facts: int

# 初始化默认设置（来自环境变量或默认值）
_SETTINGS = ContextSettings(
    recent_chapters_window=int(os.getenv("RECENT_CHAPTERS_WINDOW", "3")),
    total_context_budget_chars=int(os.getenv("TOTAL_CONTEXT_BUDGET_CHARS", "50000")),
    soft_budget_chars=int(os.getenv("SOFT_BUDGET_CHARS", "48000")),
    quota_recent=int(os.getenv("CTX_QUOTA_RECENT", "28000")),
    quota_older_summary=int(os.getenv("CTX_QUOTA_OLDER", "10000")),
    quota_facts=int(os.getenv("CTX_QUOTA_FACTS", "5000")),
)


def get_settings() -> ContextSettings:
    return _SETTINGS


def update_settings(patch: Dict[str, Any]) -> ContextSettings:
    global _SETTINGS
    data = _SETTINGS.__dict__.copy()
    for k, v in (patch or {}).items():
        if k in data and isinstance(v, int):
            data[k] = v
    _SETTINGS = ContextSettings(**data)
    return _SETTINGS

# 保留 Graphiti 开关（仍读环境变量）
USE_GRAPHITI = os.getenv("USE_GRAPHITI", "false").lower() == "true"


@dataclass
class ContextAssembleParams:
    project_id: Optional[int]
    volume_number: Optional[int]
    chapter_number: Optional[int]
    participants: Optional[List[str]]
    current_draft_tail: Optional[str]
    recent_chapters_window: Optional[int] = None
    chapter_id: Optional[int] = None


@dataclass
class AssembledContext:
    facts_subgraph: str
    budget_stats: Dict[str, Any]
    facts_structured: Optional[Dict[str, Any]] = None

    def to_system_prompt_block(self) -> str:
        parts: List[str] = []
        if self.facts_subgraph:
            parts.append(f"[事实子图]\n{self.facts_subgraph}")
        return "\n\n".join(parts)


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 200)] + "\n...[已截断]"






def _compose_facts_subgraph_stub() -> str:
    return "关键事实：暂无（Graphiti 未启用或未收集）。"


def _format_subgraph_as_text(data: Dict[str, Any]) -> str:
    nodes = data.get("nodes") or []
    edges = data.get("edges") or []
    summaries: List[str] = data.get("fact_summaries") or []
    # 将边按类型分组，便于阅读
    grouped: Dict[str, List[str]] = {}
    for e in edges:
        et = str(e.get("type") or "fact")
        fv = str(e.get("fact") or "")
        grouped.setdefault(et, []).append(fv)
    parts: List[str] = []
    # 事实摘要
    if isinstance(summaries, list) and summaries:
        parts.append("关键事实：")
        for s in summaries[:30]:
            parts.append(f"- {s}")
    # 边分组作为补充
    for et, facts in grouped.items():
        parts.append(f"{et}:")
        for f in facts[:30]:
            parts.append(f"- {f}")
    if not parts and nodes:
        lbls = [str(n.get("label") or n.get("id")) for n in nodes[:10]]
        parts.append("事实节点：" + "; ".join(lbls))
    return "\n".join(parts)


def _calc_total_size(parts: Dict[str, int]) -> int:
    return sum(parts.values())







def assemble_context(session: Session, params: ContextAssembleParams) -> AssembledContext:
    settings = get_settings()
    facts_quota = settings.quota_facts

    # 仅做事实子图装配
    # 严格使用请求传入的参与者，不再在服务端推断
    eff_participants: List[str] = list(params.participants or [])

    facts_text = _compose_facts_subgraph_stub()
    facts_structured: Optional[Dict[str, Any]] = None
    try:
        from app.services.consistency_provider import DirectKGConsistencyProvider
        provider: ConsistencyProvider = DirectKGConsistencyProvider()
        edge_whitelist = ["has_alias", "participated_in", "addressed_as", "has_enemy", "resolved_in", "located_at", "event_summary", "stance"]
        est_top_k = max(5, min(100, facts_quota // 100))
        sub_struct = provider.get_facts_structured(
            project_id=params.project_id or -1,
            participants=eff_participants,
            radius=2,
            edge_type_whitelist=edge_whitelist,
            top_k=est_top_k,
            max_chapter_id=None,
        )
        raw = sub_struct.get("_raw") or {}
        txt = _format_subgraph_as_text(raw if isinstance(raw, dict) else {})
        if txt:
            facts_text = txt
        # 用模型实例化，避免手写字段名错误
        try:
            from app.schemas.context import FactsStructured as _FactsStructured
            fs_model = _FactsStructured(
                fact_summaries=list(sub_struct.get("fact_summaries") or []),
                relation_summaries=[
                    {
                        "a": it.get("a"),
                        "b": it.get("b"),
                        "kind": it.get("kind"),
                        "a_to_b_addressing": it.get("a_to_b_addressing"),
                        "b_to_a_addressing": it.get("b_to_a_addressing"),
                        "recent_dialogues": it.get("recent_dialogues") or [],
                        "recent_event_summaries": it.get("recent_event_summaries") or [],
                    }
                    for it in (sub_struct.get("relation_summaries") or [])
                    if isinstance(it, dict)
                ],
            )
            facts_structured = fs_model.model_dump()
        except Exception:
            facts_structured = {
                "fact_summaries": sub_struct.get("fact_summaries") or [],
                "relation_summaries": sub_struct.get("relation_summaries") or [],
            }
    except Exception:
        pass

    facts = _truncate(facts_text, facts_quota)

    parts_sizes = {
        "recent_chapters_text": 0,
        "older_chapters_summary": 0,
        "facts_subgraph": len(facts),
    }
    total_size = _calc_total_size(parts_sizes)

    return AssembledContext(
        facts_subgraph=facts,
        budget_stats={
            "parts": parts_sizes,
            "total": total_size,
            "soft_budget": settings.soft_budget_chars,
            "hard_budget": settings.total_context_budget_chars,
            "recent_window_used": settings.recent_chapters_window,
        },
        facts_structured=facts_structured,
    ) 