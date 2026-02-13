from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlmodel import Session, select

from app.db.models import CardType


def list_card_types_brief(session: Session) -> List[Dict[str, Any]]:
    rows = session.exec(select(CardType)).all()
    return [
        {
            "id": row.id,
            "name": row.name,
            "model_name": row.model_name,
            "description": row.description,
            "has_schema": isinstance(row.json_schema, dict) and bool(row.json_schema),
        }
        for row in rows
    ]


def find_card_type(
    session: Session,
    card_type_name: str,
    allow_model_name: bool = True,
) -> Optional[CardType]:
    target = (card_type_name or "").strip()
    if not target:
        return None

    rows = session.exec(select(CardType)).all()
    for row in rows:
        if row.name == target:
            return row
        if allow_model_name and row.model_name == target:
            return row
    return None


def get_card_type_schema_payload(
    session: Session,
    card_type_name: str,
    allow_model_name: bool = True,
    require_schema: bool = False,
) -> Dict[str, Any]:
    target = (card_type_name or "").strip()
    if not target:
        return {"success": False, "error": "card_type_required"}

    matched = find_card_type(session, target, allow_model_name=allow_model_name)
    if not matched:
        return {"success": False, "error": "not_found", "card_type": target}

    schema = matched.json_schema if isinstance(matched.json_schema, dict) else {}
    if require_schema and not schema:
        return {
            "success": False,
            "error": "schema_not_defined",
            "card_type": matched.name,
            "model_name": matched.model_name,
        }

    return {
        "success": True,
        "card_type": matched.name,
        "model_name": matched.model_name,
        "schema": schema,
    }

