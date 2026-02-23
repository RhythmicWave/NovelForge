from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy.orm import joinedload
from sqlmodel import Session, select

from app.db.models import Card, CardType, Project
from app.exceptions import BusinessException
from app.schemas.card import CardExportRequest


@dataclass
class CardExportPayload:
    filename: str
    media_type: str
    content: bytes


class CardExportService:
    """项目卡片导出服务（范围筛选 + 格式序列化）。"""

    _MEDIA_TYPES = {
        "txt": "text/plain; charset=utf-8",
        "md": "text/markdown; charset=utf-8",
        "json": "application/json; charset=utf-8",
    }

    def __init__(self, db: Session):
        self.db = db

    def export(self, project_id: int, request: CardExportRequest) -> CardExportPayload:
        project = self.db.get(Project, project_id)
        if not project:
            raise BusinessException(f"Project with id {project_id} not found", status_code=404)

        cards = self._load_cards(project_id=project_id, request=request)
        if not cards:
            raise BusinessException("当前条件下没有可导出的卡片", status_code=404)

        exported_at = datetime.now()
        if request.format == "json":
            text = self._build_json(project=project, cards=cards, request=request, exported_at=exported_at)
        elif request.format == "md":
            text = self._build_markdown(project=project, cards=cards, request=request, exported_at=exported_at)
        else:
            text = self._build_text(project=project, cards=cards, request=request, exported_at=exported_at)

        filename = self._build_filename(
            project_name=project.name,
            request=request,
            cards=cards,
            exported_at=exported_at,
        )
        media_type = self._MEDIA_TYPES[request.format]
        return CardExportPayload(filename=filename, media_type=media_type, content=text.encode("utf-8"))

    def _load_cards(self, project_id: int, request: CardExportRequest) -> List[Card]:
        statement = (
            select(Card)
            .where(Card.project_id == project_id)
            .options(joinedload(Card.card_type))
        )

        if request.scope == "single":
            if request.card_id is None:
                raise BusinessException("scope=single 缺少 card_id", status_code=400)
            statement = statement.where(Card.id == request.card_id)
            card = self.db.exec(statement).first()
            if not card:
                raise BusinessException("目标卡片不存在或不属于当前项目", status_code=404)
            return [card]

        if request.scope == "type":
            if request.card_type_id is None:
                raise BusinessException("scope=type 缺少 card_type_id", status_code=400)
            card_type = self.db.get(CardType, request.card_type_id)
            if not card_type:
                raise BusinessException("卡片类型不存在", status_code=404)
            statement = statement.where(Card.card_type_id == request.card_type_id)

        cards = list(self.db.exec(statement).all())
        return self._sort_cards(cards)

    def _sort_cards(self, cards: List[Card]) -> List[Card]:
        if not cards:
            return []

        card_by_id = {int(c.id): c for c in cards if c.id is not None}
        children_by_parent: Dict[int | None, List[Card]] = {}
        for card in cards:
            children_by_parent.setdefault(card.parent_id, []).append(card)

        def _sort_key(card: Card):
            created_at = card.created_at.isoformat() if card.created_at else ""
            return (card.display_order, created_at, int(card.id or 0))

        for siblings in children_by_parent.values():
            siblings.sort(key=_sort_key)

        roots = []
        for card in cards:
            if card.parent_id is None or card.parent_id not in card_by_id:
                roots.append(card)
        roots.sort(key=_sort_key)

        ordered: List[Card] = []
        stack: List[Card] = list(reversed(roots))
        while stack:
            node = stack.pop()
            ordered.append(node)
            node_id = int(node.id) if node.id is not None else None
            if node_id is None:
                continue
            children = children_by_parent.get(node_id, [])
            for child in reversed(children):
                stack.append(child)

        return ordered

    def _build_filename(
        self,
        project_name: str,
        request: CardExportRequest,
        cards: List[Card],
        exported_at: datetime,
    ) -> str:
        safe_project = self._sanitize_filename(project_name) or "novelforge"
        timestamp = exported_at.strftime("%Y%m%d-%H%M%S")

        scope_segment = request.scope
        if request.scope == "single" and cards:
            scope_segment = f"single-{int(cards[0].id or 0)}"
        elif request.scope == "type" and cards:
            type_name = getattr(cards[0].card_type, "name", "") or str(cards[0].card_type_id)
            scope_segment = f"type-{self._sanitize_filename(type_name)}"

        ext = request.format
        return f"{safe_project}-cards-{scope_segment}-{timestamp}.{ext}"

    def _build_json(
        self,
        project: Project,
        cards: List[Card],
        request: CardExportRequest,
        exported_at: datetime,
    ) -> str:
        payload = {
            "project": {"id": project.id, "name": project.name},
            "scope": request.scope,
            "format": request.format,
            "exported_at": exported_at.isoformat(),
            "total_cards": len(cards),
            "cards": [self._card_to_dict(card) for card in cards],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _build_text(
        self,
        project: Project,
        cards: List[Card],
        request: CardExportRequest,
        exported_at: datetime,
    ) -> str:
        lines: List[str] = [
            "NovelForge Card Export",
            f"项目: {project.name}",
            f"导出范围: {self._scope_text(request, cards)}",
            f"导出格式: {request.format}",
            f"导出时间: {exported_at.isoformat()}",
            f"卡片数量: {len(cards)}",
            "",
        ]

        for index, card in enumerate(cards, start=1):
            lines.extend(
                [
                    "=" * 72,
                    f"[{index}] {card.title}",
                    f"类型: {self._card_type_name(card)}",
                    f"ID: {card.id}",
                    f"父级ID: {card.parent_id}",
                    f"创建时间: {card.created_at.isoformat() if card.created_at else ''}",
                    "-" * 72,
                    self._format_content(card.content),
                    "",
                ]
            )

        return "\n".join(lines).rstrip() + "\n"

    def _build_markdown(
        self,
        project: Project,
        cards: List[Card],
        request: CardExportRequest,
        exported_at: datetime,
    ) -> str:
        lines: List[str] = [
            "# NovelForge 卡片导出",
            "",
            f"- 项目：{project.name}",
            f"- 导出范围：{self._scope_text(request, cards)}",
            f"- 导出格式：{request.format}",
            f"- 导出时间：{exported_at.isoformat()}",
            f"- 卡片数量：{len(cards)}",
            "",
        ]

        for index, card in enumerate(cards, start=1):
            lines.append(f"## {index}. {card.title}")
            lines.append(f"- 类型：{self._card_type_name(card)}")
            lines.append(f"- ID：{card.id}")
            lines.append(f"- 父级ID：{card.parent_id}")
            lines.append(f"- 创建时间：{card.created_at.isoformat() if card.created_at else ''}")
            lines.append("")
            text_content = self._extract_text_content(card.content)
            if text_content is not None:
                lines.append(text_content)
            else:
                lines.append("```json")
                lines.append(json.dumps(card.content or {}, ensure_ascii=False, indent=2))
                lines.append("```")
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    def _scope_text(self, request: CardExportRequest, cards: List[Card]) -> str:
        if request.scope == "all":
            return "全部卡片"
        if request.scope == "single":
            if cards:
                return f"单个卡片（{cards[0].title}）"
            return "单个卡片"
        if request.scope == "type":
            if cards:
                return f"类型卡片（{self._card_type_name(cards[0])}）"
            return "类型卡片"
        return request.scope

    def _card_to_dict(self, card: Card) -> Dict[str, Any]:
        return {
            "id": card.id,
            "title": card.title,
            "card_type_id": card.card_type_id,
            "card_type_name": self._card_type_name(card),
            "parent_id": card.parent_id,
            "display_order": card.display_order,
            "created_at": card.created_at.isoformat() if card.created_at else None,
            "content": card.content,
        }

    def _card_type_name(self, card: Card) -> str:
        card_type = getattr(card, "card_type", None)
        if card_type and getattr(card_type, "name", None):
            return str(card_type.name)
        return str(card.card_type_id)

    def _format_content(self, content: Any) -> str:
        if content is None:
            return "(空内容)"
        text_content = self._extract_text_content(content)
        if text_content is not None:
            return text_content
        return json.dumps(content, ensure_ascii=False, indent=2)

    def _extract_text_content(self, content: Any) -> str | None:
        if isinstance(content, str):
            parsed = self._try_parse_stringified_json(content)
            if parsed is not None:
                parsed_text_content = self._extract_text_content(parsed)
                if parsed_text_content is not None:
                    return parsed_text_content
            return content
        if isinstance(content, dict):
            text_content = content.get("content")
            if isinstance(text_content, str):
                return text_content
        return None

    def _try_parse_stringified_json(self, content: str) -> Any | None:
        stripped = content.strip()
        if not stripped or stripped[0] not in ("{", "["):
            return None
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return None

    def _sanitize_filename(self, value: str) -> str:
        illegal_chars = '<>:"/\\|?*'
        sanitized = value.strip()
        for ch in illegal_chars:
            sanitized = sanitized.replace(ch, "_")
        sanitized = sanitized.replace(" ", "_")
        return sanitized
