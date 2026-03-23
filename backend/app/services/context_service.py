from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sqlmodel import Session, select

from app.db.models import Card
from app.schemas.context import ConceptSummary, FactsStructured, ItemSummary
from app.schemas.relation_extract import CN_TO_EN_KIND
from app.services.kg_provider import get_provider
from app.utils.text_utils import truncate_text


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


def _compose_facts_subgraph_stub() -> str:
	return "关键事实：暂无（尚未收集）"


def _clean_text(value: Any) -> str:
	if value is None:
		return ""
	return str(value).strip()


def _clean_list(value: Any) -> List[str]:
	if not isinstance(value, list):
		return []
	items: List[str] = []
	for item in value:
		text = _clean_text(item)
		if text:
			items.append(text)
	return items


def _card_entity_type(card: Card) -> str:
	content = card.content if isinstance(card.content, dict) else {}
	entity_type = _clean_text(content.get("entity_type"))
	if entity_type:
		return entity_type

	card_type_name = _clean_text(getattr(card.card_type, "name", ""))
	if "物品" in card_type_name:
		return "item"
	if "概念" in card_type_name:
		return "concept"

	model_name = _clean_text(getattr(card, "model_name", "") or getattr(card.card_type, "model_name", ""))
	if model_name == "ItemCard":
		return "item"
	if model_name == "ConceptCard":
		return "concept"
	return ""


def _card_name(card: Card) -> str:
	content = card.content if isinstance(card.content, dict) else {}
	return _clean_text(content.get("name")) or _clean_text(card.title)


def _collect_referenced_entity_cards(
	session: Session,
	project_id: Optional[int],
	participants: List[str],
	entity_type: str,
) -> List[Card]:
	if not project_id or not participants:
		return []

	normalized_participants = {_clean_text(name).lower() for name in participants if _clean_text(name)}
	if not normalized_participants:
		return []

	cards = session.exec(select(Card).where(Card.project_id == project_id)).all()
	matched: List[Card] = []
	for card in cards:
		if _card_entity_type(card) != entity_type:
			continue
		card_name = _card_name(card)
		if card_name and card_name.lower() in normalized_participants:
			matched.append(card)

	matched.sort(key=lambda card: (card.display_order, card.id or 0))
	return matched


def _build_item_summaries(session: Session, project_id: Optional[int], participants: List[str]) -> List[Dict[str, Any]]:
	items = _collect_referenced_entity_cards(session, project_id, participants, "item")
	summaries: List[Dict[str, Any]] = []
	for card in items:
		content = card.content if isinstance(card.content, dict) else {}
		summary = ItemSummary(
			name=_card_name(card),
			category=_clean_text(content.get("category")),
			description=_clean_text(content.get("description")),
			owner_hint=_clean_text(content.get("owner_hint")) or None,
			current_state=_clean_text(content.get("current_state")) or None,
			power_or_effect=_clean_text(content.get("power_or_effect")) or None,
			constraints=_clean_text(content.get("constraints")) or None,
			important_events=_clean_list(content.get("important_events")),
		)
		summaries.append(summary.model_dump())
	return summaries


def _build_concept_summaries(session: Session, project_id: Optional[int], participants: List[str]) -> List[Dict[str, Any]]:
	concepts = _collect_referenced_entity_cards(session, project_id, participants, "concept")
	summaries: List[Dict[str, Any]] = []
	for card in concepts:
		content = card.content if isinstance(card.content, dict) else {}
		summary = ConceptSummary(
			name=_card_name(card),
			category=_clean_text(content.get("category")),
			description=_clean_text(content.get("description")),
			rule_definition=_clean_text(content.get("rule_definition")),
			cost=_clean_text(content.get("cost")) or None,
			mastery_hint=_clean_text(content.get("mastery_hint")) or None,
			known_by=_clean_list(content.get("known_by")),
			counter_relations=_clean_list(content.get("counter_relations")),
		)
		summaries.append(summary.model_dump())
	return summaries


def assemble_context(session: Session, params: ContextAssembleParams) -> AssembledContext:
	facts_quota = 5000

	eff_participants: List[str] = list(params.participants or [])
	participant_set = {name for name in eff_participants if name}

	facts_text = _compose_facts_subgraph_stub()
	facts_structured: Optional[Dict[str, Any]] = None
	item_summaries = _build_item_summaries(session, params.project_id, eff_participants)
	concept_summaries = _build_concept_summaries(session, params.project_id, eff_participants)

	try:
		provider = get_provider()
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
				a = str(it.get("a"))
				b = str(it.get("b"))
				kind_cn = str(it.get("kind") or "其他")
				pred_en = CN_TO_EN_KIND.get(kind_cn, kind_cn)
				lines.append(f"- {a} {pred_en} {b}")
			facts_text = "\n".join(lines)
		else:
			txt = "\n".join([f"- {f}" for f in (sub_struct.get("fact_summaries") or [])])
			if txt:
				facts_text = "关键事实：\n" + txt

		try:
			fs_model = FactsStructured(
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
				item_summaries=item_summaries,
				concept_summaries=concept_summaries,
			)
			facts_structured = fs_model.model_dump()
		except Exception:
			facts_structured = {
				"fact_summaries": sub_struct.get("fact_summaries") or [],
				"relation_summaries": filtered_relation_items,
				"item_summaries": item_summaries,
				"concept_summaries": concept_summaries,
			}
	except Exception:
		if item_summaries or concept_summaries:
			facts_structured = {
				"fact_summaries": [],
				"relation_summaries": [],
				"item_summaries": item_summaries,
				"concept_summaries": concept_summaries,
			}

	facts = truncate_text(facts_text, facts_quota, suffix="\n...[已截断]")

	return AssembledContext(
		facts_subgraph=facts,
		budget_stats={},
		facts_structured=facts_structured,
	)
