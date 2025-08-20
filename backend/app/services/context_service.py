from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from sqlmodel import Session, select

from app.db.models import Card, CardType
from app.services.memory_service import MemoryService
from app.schemas.context import FactsStructured
from app.schemas.relation_extract import CN_TO_EN_KIND
from app.services.kg_provider import get_provider



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
    return "关键事实：暂无（尚未收集）。"



def assemble_context(session: Session, params: ContextAssembleParams) -> AssembledContext:
    facts_quota = 5000

    eff_participants: List[str] = list(params.participants or [])
    participant_set = set(eff_participants)

    facts_text = _compose_facts_subgraph_stub()
    facts_structured: Optional[Dict[str, Any]] = None
    try:
        provider = get_provider()
        # 放宽：边类型允许任意（排除 HAS_ALIAS），以兼容旧图/新图
        edge_whitelist = None
        est_top_k = max(5, min(100, facts_quota // 100))
        sub_struct = provider.query_subgraph(
            project_id=params.project_id or -1,
            participants=eff_participants,
            radius=2,
            edge_type_whitelist=edge_whitelist,
            top_k=est_top_k,
            max_chapter_id=None,
        )
        raw_relation_items = [it for it in (sub_struct.get("relation_summaries") or []) if isinstance(it, dict)]
        filtered_relation_items = [
            it for it in raw_relation_items
            if (str(it.get("a")) in participant_set and str(it.get("b")) in participant_set)
        ]
        if filtered_relation_items:
            lines: List[str] = ["关键事实："]
            for it in filtered_relation_items:
                a = str(it.get("a")); b = str(it.get("b")); kind_cn = str(it.get("kind") or "其他")
                pred_en = CN_TO_EN_KIND.get(kind_cn, kind_cn)
                lines.append(f"- {a} {pred_en} {b}")
            facts_text = "\n".join(lines)
        else:
            raw = sub_struct
            txt = "\n".join([f"- {f}" for f in (raw.get("fact_summaries") or [])])
            if txt:
                facts_text = "关键事实：\n" + txt
        try:
            from app.schemas.context import FactsStructured as _FactsStructured
            fs_model = _FactsStructured(
                fact_summaries=list(sub_struct.get("fact_summaries") or []),
                relation_summaries=[
                    {
                        "a": it.get("a"),
                        "b": it.get("b"),
                        "kind": it.get("kind"),
                        "description": it.get("description"),
                        "a_to_b_addressing": it.get("a_to_b_addressing"),
                        "b_to_a_addressing": it.get("b_to_a_addressing"),
                        "recent_dialogues": it.get("recent_dialogues") or [],
                        "recent_event_summaries": it.get("recent_event_summaries") or [],
                        "stance": it.get("stance"),
                    }
                    for it in filtered_relation_items
                ],
            )
            facts_structured = fs_model.model_dump()
        except Exception:
            facts_structured = {
                "fact_summaries": sub_struct.get("fact_summaries") or [],
                "relation_summaries": filtered_relation_items,
            }
    except Exception:
        pass

    facts = _truncate(facts_text, facts_quota)


    return AssembledContext(
        facts_subgraph=facts,
        budget_stats={},
        facts_structured=facts_structured,
    ) 