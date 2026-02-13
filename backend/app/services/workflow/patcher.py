from __future__ import annotations

import difflib
import hashlib
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlmodel import Session

from app.schemas.workflow_agent import WorkflowPatchOp
from app.services.workflow.parser.marker_renamer import rename_variable


_RE_NODE_OPEN = re.compile(r"^\s*#@node(?:\((.*)\))?\s*$")
_RE_NODE_CLOSE = re.compile(r"^\s*#</node>\s*$")
_RE_ASSIGNMENT = re.compile(r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+?)\s*$")


def compute_code_revision(code: str) -> str:
    digest = hashlib.sha256((code or "").encode("utf-8")).hexdigest()
    return digest[:16]


def build_code_diff(old_code: str, new_code: str) -> str:
    before = (old_code or "").splitlines(keepends=True)
    after = (new_code or "").splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(
            before,
            after,
            fromfile="workflow.before.wf",
            tofile="workflow.after.wf",
            lineterm="",
        )
    )


@dataclass
class NodeBlock:
    variable: str
    start_line: int
    end_line: int
    open_line: int
    assignment_line: int
    assignment_expr: str
    meta_raw: str


@dataclass
class PatchExecutionResult:
    new_code: str
    changed_nodes: List[str]
    applied_ops: int
    parse_result: Dict[str, Any]
    validation: Dict[str, Any]
    diff: str


def _split_meta_pairs(text: str) -> List[str]:
    result: List[str] = []
    buffer: List[str] = []
    quote: Optional[str] = None
    escaped = False
    depth = 0

    for char in text:
        if quote is not None:
            buffer.append(char)
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue

        if char in ("'", '"'):
            quote = char
            buffer.append(char)
            continue

        if char in ("(", "[", "{"):
            depth += 1
            buffer.append(char)
            continue

        if char in (")", "]", "}"):
            depth = max(0, depth - 1)
            buffer.append(char)
            continue

        if char == "," and depth == 0:
            piece = "".join(buffer).strip()
            if piece:
                result.append(piece)
            buffer = []
            continue

        buffer.append(char)

    tail = "".join(buffer).strip()
    if tail:
        result.append(tail)
    return result


def _parse_meta_value(raw: str) -> Any:
    lowered = raw.lower()
    if lowered in ("true", "yes", "on"):
        return True
    if lowered in ("false", "no", "off"):
        return False
    if raw == "1":
        return True
    if raw == "0":
        return False
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
        return raw[1:-1]
    try:
        return int(raw)
    except Exception:
        return raw


def _parse_node_meta(meta_text: str) -> Dict[str, Any]:
    meta: Dict[str, Any] = {
        "is_async": False,
        "disabled": False,
        "description": "",
        "name": None,
    }
    content = (meta_text or "").strip()
    if not content:
        return meta

    for part in _split_meta_pairs(content):
        if "=" not in part:
            continue
        key, raw = part.split("=", 1)
        key = key.strip()
        value = _parse_meta_value(raw.strip())
        if key in ("async", "is_async"):
            meta["is_async"] = bool(value)
        elif key == "disabled":
            meta["disabled"] = bool(value)
        elif key == "description":
            meta["description"] = str(value)
        elif key == "name":
            meta["name"] = str(value)
    return meta


def _render_node_meta(meta: Dict[str, Any]) -> str:
    parts: List[str] = []
    if meta.get("is_async"):
        parts.append("async=true")
    if meta.get("disabled"):
        parts.append("disabled=true")
    description = str(meta.get("description") or "")
    if description:
        escaped = description.replace("\\", "\\\\").replace('"', '\\"')
        parts.append(f'description="{escaped}"')
    name = meta.get("name")
    if name:
        parts.append(f'name="{name}"')
    if not parts:
        return "#@node()"
    return f"#@node({', '.join(parts)})"


def _normalize_block_text(block: str) -> str:
    text = block or ""
    text = text.replace("\r\n", "\n")
    if not text.endswith("\n"):
        text += "\n"
    return text


def _find_blocks(lines: Sequence[str]) -> List[NodeBlock]:
    blocks: List[NodeBlock] = []
    index = 0
    while index < len(lines):
        opening = _RE_NODE_OPEN.match(lines[index].rstrip("\n"))
        if not opening:
            index += 1
            continue

        start = index
        meta_raw = (opening.group(1) or "").strip()
        index += 1
        while index < len(lines) and not _RE_NODE_CLOSE.match(lines[index].rstrip("\n")):
            index += 1
        if index >= len(lines):
            break
        end = index

        variable = ""
        assignment_line = -1
        assignment_expr = ""
        for i in range(start + 1, end):
            raw = lines[i].rstrip("\n")
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            matched = _RE_ASSIGNMENT.match(raw)
            if matched:
                variable = matched.group(1)
                assignment_expr = matched.group(2).strip()
                assignment_line = i
                break

        if not variable:
            meta_name = _parse_node_meta(meta_raw).get("name")
            variable = str(meta_name or "")

        if variable:
            blocks.append(
                NodeBlock(
                    variable=variable,
                    start_line=start,
                    end_line=end,
                    open_line=start,
                    assignment_line=assignment_line,
                    assignment_expr=assignment_expr,
                    meta_raw=meta_raw,
                )
            )
        index = end + 1
    return blocks


def _rebuild_lines_from_code(code: str) -> List[str]:
    lines = (code or "").splitlines(keepends=True)
    if not lines:
        return [""]
    return lines


def _insert_block(
    lines: List[str],
    target: NodeBlock,
    block_text: str,
    *,
    before: bool,
) -> List[str]:
    insert_at = target.start_line if before else target.end_line + 1
    normalized = _normalize_block_text(block_text)
    block_lines = normalized.splitlines(keepends=True)
    if insert_at > 0 and lines[insert_at - 1].strip() and block_lines and block_lines[0].strip():
        block_lines = ["\n", *block_lines]
    if insert_at < len(lines) and lines[insert_at].strip() and block_lines and block_lines[-1].strip():
        block_lines = [*block_lines, "\n"]
    return [*lines[:insert_at], *block_lines, *lines[insert_at:]]


def apply_patch_ops(code: str, patch_ops: Sequence[WorkflowPatchOp]) -> Tuple[str, List[str], int]:
    lines = _rebuild_lines_from_code(code)
    changed_nodes: List[str] = []
    applied_ops = 0

    alias_map = {
        "replace": "replace_code",
        "replace_all": "replace_code",
        "full_replace": "replace_code",
        "replace_workflow": "replace_code",
    }

    for op in patch_ops:
        op_name = (op.op or "").strip()
        op_name = alias_map.get(op_name, op_name)

        if op_name == "replace_code":
            full_code = (op.new_code or "").strip()
            if not full_code and op.new_block:
                full_code = op.new_block

            if not full_code:
                raise ValueError("replace_code 缺少 new_code")

            lines = _rebuild_lines_from_code(full_code)
            changed_nodes.append("__all__")
            applied_ops += 1
            continue

        blocks = _find_blocks(lines)

        if op_name in ("insert_node_before", "insert_node_after"):
            if not op.target_node or not op.new_block:
                raise ValueError(f"{op_name} 缺少 target_node 或 new_block")
            target = next((b for b in blocks if b.variable == op.target_node), None)
            if not target:
                raise ValueError(f"未找到目标节点: {op.target_node}")
            lines = _insert_block(lines, target, op.new_block, before=(op_name == "insert_node_before"))
            new_blocks = _find_blocks(_rebuild_lines_from_code("".join(lines)))
            inserted = [b.variable for b in new_blocks if b.variable not in {x.variable for x in blocks}]
            changed_nodes.extend(inserted or [op.target_node])
            applied_ops += 1
            continue

        if op_name == "delete_node":
            if not op.target_node:
                raise ValueError("delete_node 缺少 target_node")
            target = next((b for b in blocks if b.variable == op.target_node), None)
            if not target:
                raise ValueError(f"未找到目标节点: {op.target_node}")
            lines = [*lines[:target.start_line], *lines[target.end_line + 1 :]]
            changed_nodes.append(op.target_node)
            applied_ops += 1
            continue

        if op_name == "update_node_meta":
            if not op.target_node:
                raise ValueError("update_node_meta 缺少 target_node")
            target = next((b for b in blocks if b.variable == op.target_node), None)
            if not target:
                raise ValueError(f"未找到目标节点: {op.target_node}")
            current_meta = _parse_node_meta(target.meta_raw)
            merged = {**current_meta, **(op.new_meta or {})}
            rendered = _render_node_meta(merged)
            line_ending = "\n" if lines[target.open_line].endswith("\n") else ""
            lines[target.open_line] = rendered + line_ending
            changed_nodes.append(op.target_node)
            applied_ops += 1
            continue

        if op_name == "update_node_call":
            if not op.target_node or not op.new_call:
                raise ValueError("update_node_call 缺少 target_node 或 new_call")
            target = next((b for b in blocks if b.variable == op.target_node), None)
            if not target:
                raise ValueError(f"未找到目标节点: {op.target_node}")
            if target.assignment_line < 0:
                raise ValueError(f"节点缺少赋值语句: {op.target_node}")

            current_meta = _parse_node_meta(target.meta_raw)
            rendered_meta = _render_node_meta(current_meta)

            call_lines = (op.new_call or "").replace("\r\n", "\n").split("\n")
            while call_lines and not call_lines[-1].strip():
                call_lines.pop()
            if not call_lines:
                raise ValueError("update_node_call 的 new_call 为空")

            rebuilt_block: List[str] = [rendered_meta + "\n"]
            rebuilt_block.append(f"{target.variable} = {call_lines[0]}\n")
            for extra_line in call_lines[1:]:
                rebuilt_block.append(extra_line + "\n")
            rebuilt_block.append("#</node>\n")

            lines = [*lines[: target.start_line], *rebuilt_block, *lines[target.end_line + 1 :]]
            changed_nodes.append(op.target_node)
            applied_ops += 1
            continue

        if op_name == "rename_variable":
            if not op.old_name or not op.new_name:
                raise ValueError("rename_variable 缺少 old_name 或 new_name")
            current_code = "".join(lines)
            renamed = rename_variable(current_code, op.old_name, op.new_name)
            lines = _rebuild_lines_from_code(renamed)
            changed_nodes.extend([op.old_name, op.new_name])
            applied_ops += 1
            continue

        raise ValueError(f"不支持的 patch op: {op_name}")

    dedup_changed_nodes: List[str] = []
    seen = set()
    for node in changed_nodes:
        if node not in seen:
            seen.add(node)
            dedup_changed_nodes.append(node)

    return "".join(lines), dedup_changed_nodes, applied_ops


def parse_workflow_code_to_result(code: str) -> Dict[str, Any]:
    """Parse workflow code and return a normalized parse result payload."""
    try:
        from app.services.workflow.parser.marker_parser import WorkflowParser

        parser = WorkflowParser()
        plan = parser.parse(code or "")
        return {
            "ok": True,
            "statements": [
                {
                    "variable": stmt.variable,
                    "code": getattr(stmt, "code", None),
                    "line": stmt.line_number,
                    "node_type": stmt.node_type,
                    "config": getattr(stmt, "config", None),
                    "is_async": stmt.is_async,
                    "disabled": stmt.disabled,
                    "description": getattr(stmt, "description", "") or "",
                }
                for stmt in plan.statements
            ],
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def execute_patch_with_validation(
    old_code: str,
    patch_ops: Sequence[WorkflowPatchOp],
    session: Optional[Session] = None,
) -> PatchExecutionResult:
    new_code, changed_nodes, applied_ops = apply_patch_ops(old_code, patch_ops)

    parse_result = parse_workflow_code_to_result(new_code)

    from app.services.workflow.validator import validate_workflow

    validation = validate_workflow(new_code, session=session).to_dict()
    diff = build_code_diff(old_code, new_code)

    return PatchExecutionResult(
        new_code=new_code,
        changed_nodes=changed_nodes,
        applied_ops=applied_ops,
        parse_result=parse_result,
        validation=validation,
        diff=diff,
    )
