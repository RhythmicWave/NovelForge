from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from sqlmodel import Session

from loguru import logger

from app.schemas.relation_extract import RelationExtraction, CN_TO_EN_KIND
from app.services import agent_service
from pydantic import BaseModel
# 新增：引入动态信息模型
from app.schemas.entity import UpdateDynamicInfo, DynamicInfoType, DynamicInfoItem
from app.db.models import Card, CardType
from sqlmodel import select

# 新增：从数据库加载提示词
from app.services import prompt_service

# 新增：使用可切换的知识图谱 Provider
from app.services.kg_provider import get_provider, KnowledgeGraphUnavailableError


class MemoryService:
    def __init__(self, session: Session):
        self.session = session
        self.graph = get_provider()

    async def extract_relations_llm(self, text: str, participants: Optional[List[str]] = None, llm_config_id: int = 1, timeout: Optional[float] = None, prompt_name: Optional[str] = "relation_extraction") -> RelationExtraction:
        # 优先使用默认提示词，如果不存在则回退到硬编码版本
        prompt = prompt_service.get_prompt_by_name(self.session, prompt_name)
        system_prompt = prompt.template
        
        # 将输出模型的 JSON Schema 附加到系统提示词中
        schema_json = RelationExtraction.model_json_schema()
        system_prompt += f"\n\n请严格按照以下 JSON Schema 格式进行输出:\n{schema_json}"

        user_prompt = (
            f"参与者: {', '.join(participants or [])}\n\n"
            "请从以下正文中抽取：\n"
            f"正文：\n{text}"
        )
        res = await agent_service.run_llm_agent(
            session=self.session,
            llm_config_id=llm_config_id,
            user_prompt=user_prompt,
            output_type=RelationExtraction,
            system_prompt=system_prompt,
            timeout=timeout,
        )
        if not isinstance(res, RelationExtraction):
            raise ValueError("LLM 关系抽取失败：输出格式不符合 RelationExtraction")
        return res

    async def extract_dynamic_info_from_text(self, text: str, participants: Optional[List[str]] = None, llm_config_id: int = 1, timeout: Optional[float] = None, prompt_name: Optional[str] = "dynamic_info_extraction", project_id: Optional[int] = None, extra_context: Optional[str] = None) -> UpdateDynamicInfo:
        """从文本中为指定参与者抽取动态信息。extra_context 由前端拼装（可包含分卷主线/支线、阶段概述等任意文本）。"""
        prompt = prompt_service.get_prompt_by_name(self.session, prompt_name)
        if not prompt:
            raise ValueError(f"未找到提示词: {prompt_name}")
        system_prompt = prompt.template

        # 附加 JSON Schema 以强化输出结构
        schema_json = UpdateDynamicInfo.model_json_schema()
        system_prompt += f"\n\n请严格按照以下 JSON Schema 格式进行输出:\n{schema_json}"

        # 参考上下文（完全由前端决定）+ 现有角色动态信息
        ref_blocks: List[str] = []
        if extra_context:
            ref_blocks.append(f"【大纲参考信息】\n{extra_context}")
        if project_id and participants:
            try:
                # 查询“角色卡”类型
                ct_stmt = select(CardType).where(CardType.name == "角色卡")
                ct = self.session.exec(ct_stmt).first()
                if ct:
                    lines: List[str] = []
                    for name in participants:
                        st = select(Card).where(Card.project_id == project_id, Card.card_type_id == ct.id, Card.title == name)
                        card = self.session.exec(st).first()
                        if not card:
                            continue
                        try:
                            from app.schemas.entity import CharacterCard
                            model = CharacterCard.model_validate(card.content or {})
                            di = model.dynamic_info or {}
                            if not di:
                                continue
                            lines.append(f"- {name}:")
                            for k, items in di.items():
                                if not items:
                                    continue
                                cat = k.value if hasattr(k, 'value') else str(k)
                                brief = "; ".join([f"[{it.id}] {it.info} (w={getattr(it, 'weight', 0):.2f})" for it in items[:5]])
                                lines.append(f"  • {cat}: {brief}")
                        except Exception:
                            continue
                    if lines:
                        ref_blocks.append("【现有角色动态信息（只读参考）】\n" + "\n".join(lines))
            except Exception:
                pass

        ref_text = ("\n\n".join(ref_blocks) + "\n\n") if ref_blocks else ""

        logger.info(f"================ref_text: {ref_text}")

        user_prompt = (
            f"{ref_text}"
            f"请为以下参与者抽取动态信息：\n"
            f"{', '.join(participants or [])}\n\n"
            f"章节正文：\n"
            f"{text}"
        )

        res = await agent_service.run_llm_agent(
            session=self.session,
            llm_config_id=llm_config_id,
            user_prompt=user_prompt,
            output_type=UpdateDynamicInfo,
            system_prompt=system_prompt,
            timeout=timeout,
        )

        if not isinstance(res, UpdateDynamicInfo):
            raise ValueError("LLM 动态信息抽取失败：输出格式不符合 UpdateDynamicInfo")
        
        return res

    def query_subgraph(
        self,
        project_id: int,
        participants: Optional[List[str]] = None,
        radius: int = 2,
        edge_type_whitelist: Optional[List[str]] = None,
        top_k: int = 50,
        max_chapter_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        return self.graph.query_subgraph(
            project_id=project_id,
            participants=participants,
            radius=radius,
            edge_type_whitelist=edge_type_whitelist,
            top_k=top_k,
            max_chapter_id=max_chapter_id,
        )

    def ingest_relations_from_llm(self, project_id: int, data: RelationExtraction, *, volume_number: Optional[int] = None, chapter_number: Optional[int] = None) -> Dict[str, Any]:
        # 写入关系三元组；同时最小持久化称呼/事件摘要/立场（作为可检索证据）
        # tuples: (主体, 关系, 客体, 属性字典)
        triples_with_attrs: List[tuple[str, str, str, Dict[str, Any]]] = []

        DIALOGUES_QUEUE_SIZE = 5
        EVENTS_QUEUE_SIZE = 5

        def _merge_queue(existing: List[Any], incoming: List[Any], key_fn=lambda x: x, max_size: int = 3) -> List[Any]:
            seen = set()
            merged: List[Any] = []
            # 先旧后新，保持“新在队尾”，之后裁剪保留队尾（最近）
            for it in (existing or []) + (incoming or []):
                k = key_fn(it)
                if k in seen:
                    continue
                seen.add(k)
                merged.append(it)
            if len(merged) <= max_size:
                return merged
            return merged[-max_size:]

        # 按队列策略合并对话/事件摘要（size=3），并序列化为字典
        merged_evidence_map: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

        # 预取：将本批所有 (a, b, kind_cn) 收集，做一次子图查询后在内存中过滤，避免多次往返
        pairs: List[Tuple[str, str, str]] = []  # (a, b, kind_en)
        for r in (data.relations or []):
            pred = CN_TO_EN_KIND.get(r.kind or '', '')
            if pred:
                pairs.append((r.a, r.b, pred))

        # 构建现存数据索引：key=(a,b,kind_en) -> {recent_dialogues, recent_event_summaries}
        existing_index: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        try:
            # 参与者全集（去重）
            all_parts = list({p for t in pairs for p in (t[0], t[1])})
            if all_parts:
                sub = self.graph.query_subgraph(project_id=project_id, participants=all_parts, top_k=200)
                from app.schemas.relation_extract import EN_TO_CN_KIND
                for item in (sub.get("relation_summaries") or []):
                    try:
                        a0 = item.get("a"); b0 = item.get("b"); kind_cn = item.get("kind")
                        kind_en = CN_TO_EN_KIND.get(kind_cn or '', '')
                        if not (a0 and b0 and kind_en):
                            continue
                        key = (a0, b0, kind_en)
                        existing_index[key] = {
                            "recent_dialogues": item.get("recent_dialogues") or [],
                            "recent_event_summaries": item.get("recent_event_summaries") or [],
                        }
                    except Exception:
                        continue
        except Exception:
            existing_index = {}

        for r in (data.relations or []):
            pred = CN_TO_EN_KIND.get(r.kind or '', '')
            if not pred:
                continue
            
            # 准备属性字典（本次新增）
            attributes = r.model_dump(exclude={"a", "b", "kind"}, exclude_none=True)

            # 新增对话（过滤长度）
            new_dialogues = [d.strip() for d in (r.recent_dialogues or []) if isinstance(d, str) and len(d.strip()) >= 20]

            # 新增事件摘要（补全卷章）
            new_summaries: List[Dict[str, Any]] = []
            for s in (r.recent_event_summaries or []):
                try:
                    item = s.model_dump()
                    if volume_number is not None and item.get("volume_number") is None:
                        item["volume_number"] = int(volume_number)
                    if chapter_number is not None and item.get("chapter_number") is None:
                        item["chapter_number"] = int(chapter_number)
                    if str(item.get("summary") or "").strip():
                        new_summaries.append(item)
                except Exception:
                    continue

            # 读取现存并合并为队列
            key = (r.a, r.b, pred)
            prev = existing_index.get(key, {})
            old_dialogues: List[str] = list(prev.get("recent_dialogues") or [])
            old_summaries: List[Dict[str, Any]] = list(prev.get("recent_event_summaries") or [])

            merged_dialogues = _merge_queue(old_dialogues, new_dialogues, key_fn=lambda x: x, max_size=DIALOGUES_QUEUE_SIZE)
            merged_summaries = _merge_queue(old_summaries, new_summaries, key_fn=lambda x: (x.get("summary") or ""), max_size=EVENTS_QUEUE_SIZE)

            if merged_dialogues:
                attributes["recent_dialogues"] = merged_dialogues
            if merged_summaries:
                attributes["recent_event_summaries"] = merged_summaries

            # 清理空字段
            if not attributes.get("recent_dialogues") and "recent_dialogues" in attributes:
                attributes.pop("recent_dialogues", None)
            if not attributes.get("recent_event_summaries") and "recent_event_summaries" in attributes:
                attributes.pop("recent_event_summaries", None)
            
            triples_with_attrs.append((r.a, pred, r.b, attributes))
            
            # 返回值（仅摘要）
            merged_evidence_map[key] = {
                "recent_dialogues": attributes.get("recent_dialogues", []),
                "recent_event_summaries": [s.get('summary') for s in attributes.get("recent_event_summaries", [])]
            }

        if triples_with_attrs:
            try:
                self.graph.ingest_triples_with_attributes(project_id, triples_with_attrs)
            except Exception as e:
                raise ValueError(f"知识图谱写入失败: {e}")
        
        return {"written": len(triples_with_attrs), "merged_evidence": merged_evidence_map} 