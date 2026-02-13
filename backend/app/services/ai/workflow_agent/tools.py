from __future__ import annotations

from contextvars import ContextVar
import json
import re
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool
from loguru import logger
from sqlmodel import Session

from app.db.models import Workflow
from app.services.ai.card_type_schema import (
    get_card_type_schema_payload,
    list_card_types_brief,
)
from app.schemas.response_registry import RESPONSE_MODEL_MAP
from app.schemas.workflow_agent import WorkflowPatchOp
from app.services.workflow import get_all_node_metadata
from app.services.workflow.patcher import (
    compute_code_revision,
    execute_patch_with_validation,
    parse_workflow_code_to_result,
)


class WorkflowAgentDeps:
    def __init__(self, session: Session, workflow_id: int):
        self.session = session
        self.workflow_id = workflow_id


_workflow_agent_deps_var: ContextVar[WorkflowAgentDeps | None] = ContextVar(
    "workflow_agent_deps", default=None
)


def set_workflow_agent_deps(deps: WorkflowAgentDeps) -> None:
    _workflow_agent_deps_var.set(deps)


def _get_deps() -> WorkflowAgentDeps:
    deps = _workflow_agent_deps_var.get()
    if deps is None:
        raise RuntimeError("WorkflowAgentDeps not set")
    return deps


def _get_workflow_or_raise(session: Session, workflow_id: int) -> Workflow:
    workflow = session.get(Workflow, workflow_id)
    if not workflow:
        raise ValueError(f"Workflow not found: {workflow_id}")
    return workflow


def _normalize_patch_op_dict(raw: Dict[str, Any]) -> Dict[str, Any]:
    item = dict(raw or {})
    op = str(item.get("op") or "").strip()
    alias_map = {
        "replace": "replace_code",
        "replace_all": "replace_code",
        "full_replace": "replace_code",
        "replace_workflow": "replace_code",
    }
    op = alias_map.get(op, op)
    item["op"] = op

    if op == "replace_code" and not item.get("new_code"):
        extracted = _extract_code_text(item)
        if extracted:
            item["new_code"] = extracted

    if op == "replace_code" and isinstance(item.get("new_code"), str):
        item["new_code"] = _normalize_code_text(item.get("new_code") or "")

    return item


def _extract_code_text(value: Any) -> Optional[str]:
    if value is None:
        return None

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.startswith("{") and text.endswith("}"):
            try:
                payload = json.loads(text)
                nested = _extract_code_text(payload)
                if nested:
                    return nested
            except Exception:
                pass
        return text

    if isinstance(value, dict):
        direct_keys = (
            "new_code",
            "code",
            "full_code",
            "workflow_code",
            "new_workflow_code",
            "new_block",
            "content",
            "text",
        )
        for key in direct_keys:
            nested = _extract_code_text(value.get(key))
            if nested:
                return nested

        nested_keys = ("args", "input", "payload", "data")
        for key in nested_keys:
            nested = _extract_code_text(value.get(key))
            if nested:
                return nested

        return None

    return None


def _coerce_patch_ops(payload: Any) -> List[Dict[str, Any]]:
    source = payload

    if isinstance(source, str):
        text = source.strip()
        if not text:
            return []
        try:
            source = json.loads(text)
        except Exception:
            return []

    if isinstance(source, dict):
        if isinstance(source.get("patch_ops"), list):
            source = source.get("patch_ops")
        elif isinstance(source.get("ops"), list):
            source = source.get("ops")
        elif source.get("op"):
            source = [source]
        else:
            return []

    if not isinstance(source, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for item in source:
        current = item
        if isinstance(current, str):
            text = current.strip()
            if not text:
                continue
            try:
                current = json.loads(text)
            except Exception:
                continue

        if isinstance(current, dict):
            normalized.append(dict(current))

    return normalized


def _normalize_code_text(code: str) -> str:
    text = str(code or "").lstrip("\ufeff").strip()

    if not text:
        return text

    text = (
        text.replace("“", '"')
        .replace("”", '"')
        .replace("‘", "'")
        .replace("’", "'")
    )

    fenced = re.match(r"^```(?:python|wf|json)?\s*([\s\S]*?)\s*```$", text, flags=re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()

    if text.startswith("{") and text.endswith("}"):
        try:
            payload = json.loads(text)
            if isinstance(payload, dict):
                for key in ("new_code", "code", "full_code"):
                    value = payload.get(key)
                    if isinstance(value, str) and value.strip():
                        text = value.strip()
                        break
        except Exception:
            pass

    if text.startswith('"') and text.endswith('"'):
        try:
            loaded = json.loads(text)
            if isinstance(loaded, str) and loaded.strip():
                text = loaded.strip()
        except Exception:
            pass

    text = text.replace("\r\n", "\n")
    lines = text.split("\n")
    normalized_lines: List[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped == "</node>":
            normalized_lines.append("#</node>")
        else:
            normalized_lines.append(line)

    return "\n".join(normalized_lines).strip()


def _apply_patch_preview(
    *,
    workflow: Workflow,
    session: Session,
    base_revision: str,
    patch_ops: List[Dict[str, Any]],
) -> Dict[str, Any]:
    old_code = workflow.definition_code or ""
    current_revision = compute_code_revision(old_code)
    if base_revision != current_revision:
        logger.warning(
            "[WorkflowAgent] preview base_revision mismatch, auto-rebase {} -> {}",
            base_revision,
            current_revision,
        )

    try:
        normalized_ops = [_normalize_patch_op_dict(item or {}) for item in (patch_ops or [])]
        filtered_ops: List[Dict[str, Any]] = []
        dropped_replace_ops: List[int] = []
        for index, item in enumerate(normalized_ops):
            op_name = str(item.get("op") or "").strip()
            if op_name == "replace_code":
                new_code = item.get("new_code")
                if not isinstance(new_code, str) or not new_code.strip():
                    dropped_replace_ops.append(index)
                    continue
            filtered_ops.append(item)

        if dropped_replace_ops and not filtered_ops:
            return {
                "success": False,
                "error": "replace_code_missing_new_code",
                "message": "replace_code requires a non-empty new_code.",
                "base_revision": current_revision,
                "patch_ops": normalized_ops,
                "invalid_replace_op_indexes": dropped_replace_ops,
                "applied_ops": 0,
                "changed_nodes": [],
                "new_code": "",
                "diff": "",
                "parse": {"ok": False, "error": "replace_code_missing_new_code"},
                "validation": {"is_valid": False, "errors": ["replace_code_missing_new_code"]},
            }

        if dropped_replace_ops:
            logger.warning(
                "[WorkflowAgent] dropped invalid replace_code ops missing new_code: {}",
                dropped_replace_ops,
            )

        normalized_ops = filtered_ops
        parsed_ops = [WorkflowPatchOp.model_validate(item) for item in normalized_ops]
        result = execute_patch_with_validation(old_code, parsed_ops, session=session)
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "base_revision": current_revision,
            "patch_ops": patch_ops or [],
            "applied_ops": 0,
            "changed_nodes": [],
            "new_code": "",
            "diff": "",
            "parse": {"ok": False, "error": str(exc)},
            "validation": {"is_valid": False, "errors": [str(exc)]},
        }

    parse_ok = bool(result.parse_result.get("ok"))
    return {
        "success": parse_ok and bool(result.validation.get("is_valid", False)),
        "base_revision": current_revision,
        "new_revision": compute_code_revision(result.new_code),
        "patch_ops": [item.model_dump(exclude_none=True) for item in parsed_ops],
        "applied_ops": result.applied_ops,
        "changed_nodes": result.changed_nodes,
        "new_code": result.new_code,
        "diff": result.diff,
        "parse": result.parse_result,
        "validation": result.validation,
    }


@tool
def wf_get_current_code(workflow_id: Optional[int] = None) -> Dict[str, Any]:
    """Read current workflow code and revision."""
    deps = _get_deps()
    target_id = workflow_id or deps.workflow_id
    workflow = _get_workflow_or_raise(deps.session, target_id)
    code = workflow.definition_code or ""
    return {
        "success": True,
        "workflow_id": workflow.id,
        "name": workflow.name,
        "code": code,
        "revision": compute_code_revision(code),
    }


@tool
def wf_parse_code(code: str) -> Dict[str, Any]:
    """Parse workflow code and return statement summary."""
    parsed = parse_workflow_code_to_result(code)
    if not parsed.get("ok"):
        return {"success": False, "error": parsed.get("error")}
    return {
        "success": True,
        "parse": parsed,
        "statements": parsed.get("statements", []),
    }


@tool
def wf_validate_code(code: str) -> Dict[str, Any]:
    """Validate workflow code and return structured result."""
    from app.services.workflow.validator import validate_workflow

    deps = _get_deps()
    result = validate_workflow(code or "", session=deps.session)
    return {"success": True, "validation": result.to_dict()}


@tool
def wf_apply_patch(
    base_revision: str,
    patch_ops: Any,
    workflow_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Apply patch_ops to code (preview only), then parse + validate."""
    deps = _get_deps()
    target_id = workflow_id or deps.workflow_id
    workflow = _get_workflow_or_raise(deps.session, target_id)
    normalized_patch_ops = _coerce_patch_ops(patch_ops)
    if not normalized_patch_ops:
        return {
            "success": False,
            "error": "patch_ops_empty",
            "message": "wf_apply_patch requires patch_ops list.",
            "base_revision": compute_code_revision(workflow.definition_code or ""),
            "patch_ops": [],
            "applied_ops": 0,
            "changed_nodes": [],
            "new_code": "",
            "diff": "",
            "parse": {"ok": False, "error": "patch_ops_empty"},
            "validation": {"is_valid": False, "errors": ["patch_ops_empty"]},
        }

    return _apply_patch_preview(
        workflow=workflow,
        session=deps.session,
        base_revision=base_revision,
        patch_ops=normalized_patch_ops,
    )


@tool
def wf_replace_code(
    base_revision: str,
    new_code: Any = None,
    workflow_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Replace workflow code using full new_code, then parse + validate (preview only)."""
    deps = _get_deps()
    target_id = workflow_id or deps.workflow_id
    workflow = _get_workflow_or_raise(deps.session, target_id)

    normalized_new_code = _extract_code_text(new_code)
    if not normalized_new_code:
        return {
            "success": False,
            "error": "replace_code_missing_new_code",
            "message": "wf_replace_code requires non-empty new_code.",
            "base_revision": compute_code_revision(workflow.definition_code or ""),
            "patch_ops": [],
            "applied_ops": 0,
            "changed_nodes": [],
            "new_code": "",
            "diff": "",
            "parse": {"ok": False, "error": "replace_code_missing_new_code"},
            "validation": {"is_valid": False, "errors": ["replace_code_missing_new_code"]},
        }

    return _apply_patch_preview(
        workflow=workflow,
        session=deps.session,
        base_revision=base_revision,
        patch_ops=[{"op": "replace_code", "new_code": _normalize_code_text(normalized_new_code)}],
    )


@tool
def wf_list_node_briefs() -> Dict[str, Any]:
    """List brief metadata of all workflow nodes."""
    node_types = get_all_node_metadata()
    return {
        "success": True,
        "node_types": [
            {
                "type": item.type,
                "label": item.label,
                "category": item.category,
                "description": item.description,
            }
            for item in node_types
        ],
    }


@tool
def wf_get_node_metadata(node_types: List[str]) -> Dict[str, Any]:
    """Fetch full metadata for requested node types."""
    all_map = {item.type: item for item in get_all_node_metadata()}
    payload: Dict[str, Any] = {}
    missing: List[str] = []

    for node_type in node_types or []:
        item = all_map.get(node_type)
        if not item:
            missing.append(node_type)
            continue
        payload[node_type] = {
            "type": item.type,
            "label": item.label,
            "category": item.category,
            "description": item.description,
            "documentation": item.documentation,
            "input_schema": item.input_schema,
            "output_schema": item.output_schema,
        }

    return {"success": True, "metadata": payload, "missing": missing}


@tool
def wf_list_response_models() -> Dict[str, Any]:
    """List available response model names."""
    return {"success": True, "models": list(RESPONSE_MODEL_MAP.keys())}


@tool
def wf_get_response_model_schema(model_name: str) -> Dict[str, Any]:
    """Get JSON schema for a response model."""
    if model_name not in RESPONSE_MODEL_MAP:
        return {"success": False, "error": "not_found", "model_name": model_name}
    model_cls = RESPONSE_MODEL_MAP[model_name]
    schema = model_cls.model_json_schema(ref_template="#/$defs/{model}")
    return {"success": True, "model_name": model_name, "schema": schema}


@tool
def wf_list_card_types() -> Dict[str, Any]:
    """List available card types with names and model names."""
    deps = _get_deps()
    return {
        "success": True,
        "card_types": list_card_types_brief(deps.session),
    }


@tool
def wf_get_card_type_schema(card_type: str) -> Dict[str, Any]:
    """Get JSON schema for a card type by name or model_name."""
    deps = _get_deps()
    return get_card_type_schema_payload(
        deps.session,
        card_type,
        allow_model_name=True,
        require_schema=False,
    )


WORKFLOW_AGENT_TOOLS = [
    wf_get_current_code,
    wf_parse_code,
    wf_validate_code,
    wf_replace_code,
    wf_apply_patch,
    wf_get_node_metadata,
    wf_list_card_types,
    wf_get_card_type_schema,
    wf_list_response_models,
    wf_get_response_model_schema,
]


WORKFLOW_AGENT_TOOL_REGISTRY = {tool.name: tool for tool in WORKFLOW_AGENT_TOOLS}


WORKFLOW_AGENT_TOOL_DESCRIPTIONS = {
    tool.name: {"description": tool.description, "args": tool.args}
    for tool in WORKFLOW_AGENT_TOOLS
}


def debug_tools_loaded() -> None:
    logger.info("[WorkflowAgent] tools loaded: {}", list(WORKFLOW_AGENT_TOOL_REGISTRY.keys()))
