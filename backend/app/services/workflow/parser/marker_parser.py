"""工作流 DSL 解析器（注释标记 DSL）。

仅支持如下节点块格式：
1) 注释标记节点块（唯一受支持格式）
   #@node(async=true, disabled=false, description="...")
   var_name = Category.NodeType(...)
   #</node>

不支持 XML 节点格式（<node ...>...</node>）。
"""

import ast
import re
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from ..engine.execution_plan import ExecutionPlan, Statement
from ..expressions.builtins import get_safe_global_names


class WorkflowParser:
    """工作流解析器（注释标记 DSL）。"""

    _RE_NODE_OPEN = re.compile(r"^\s*#@node(?:\((.*)\))?\s*$")
    _RE_NODE_CLOSE = re.compile(r"^\s*#</node>\s*$")

    def parse(self, code: str) -> ExecutionPlan:
        """解析工作流代码。"""
        if not code or not code.strip():
            return ExecutionPlan(statements=[], dependencies={})

        # 兼容 UTF-8 BOM，避免首行标记被误判
        code = code.lstrip("\ufeff")

        if self._looks_like_xml(code):
            raise ValueError("不再支持 XML 工作流格式。请使用 #@node(...) ... #</node> 注释标记 DSL。")

        if not self._looks_like_marker_dsl(code):
            raise ValueError("工作流代码必须使用 #@node(...) ... #</node> 注释标记 DSL。")

        statements = self._parse_marker_dsl(code)
        dependencies = {stmt.variable: stmt.depends_on for stmt in statements}
        plan = ExecutionPlan(statements=statements, dependencies=dependencies)
        plan.validate()

        logger.debug(f"[WorkflowParser] 解析成功，模式=marker, 节点数={len(statements)}")
        return plan

    def _looks_like_xml(self, code: str) -> bool:
        return bool(re.search(r"<\s*node\b", code))

    def _looks_like_marker_dsl(self, code: str) -> bool:
        return bool(re.search(r"^\s*#@node(?:\(|\s*$)", code, re.MULTILINE))

    def _parse_marker_dsl(self, code: str) -> List[Statement]:
        lines = code.splitlines()
        statements: List[Statement] = []
        index = 0

        while index < len(lines):
            line = lines[index]
            match = self._RE_NODE_OPEN.match(line)
            if not match:
                stripped = line.strip()
                if stripped.startswith("#") or not stripped:
                    index += 1
                    continue

                raise ValueError(
                    f"第 {index + 1} 行存在未包裹在节点块中的代码。请使用 #@node(...) 与 #</node> 包裹节点。"
                )

            meta = self._parse_node_meta(match.group(1) or "")
            open_line_no = index + 1
            index += 1

            block_lines: List[str] = []
            while index < len(lines) and not self._RE_NODE_CLOSE.match(lines[index]):
                block_lines.append(lines[index])
                index += 1

            if index >= len(lines):
                raise ValueError(f"节点元数据（第 {open_line_no} 行）缺少结束标记 '#</node>'")

            index += 1
            code_block = "\n".join(block_lines)
            if not code_block:
                raise ValueError(f"节点元数据（第 {open_line_no} 行）后没有节点代码")

            stmt = self._parse_python_node_block(
                code_block=code_block,
                line_number=open_line_no,
                fallback_name=meta.get("name"),
                is_async=bool(meta.get("is_async", False)),
                disabled=bool(meta.get("disabled", False)),
                description=str(meta.get("description", "") or ""),
            )
            statements.append(stmt)

        return statements

    def _parse_node_meta(self, meta_text: str) -> Dict[str, Any]:
        meta: Dict[str, Any] = {
            "is_async": False,
            "disabled": False,
            "description": "",
            "name": None,
        }

        content = (meta_text or "").strip()
        if not content:
            return meta

        parts = self._split_meta_pairs(content)
        for part in parts:
            if not part:
                continue
            if "=" not in part:
                raise ValueError(f"无效的节点元数据片段: '{part}'（应为 key=value）")

            key, raw_value = part.split("=", 1)
            key = key.strip()
            value = self._parse_meta_value(raw_value.strip())

            if key in ("async", "is_async"):
                meta["is_async"] = self._to_bool(value, field_name=key)
            elif key == "disabled":
                meta["disabled"] = self._to_bool(value, field_name=key)
            elif key == "description":
                meta["description"] = str(value)
            elif key == "name":
                meta["name"] = str(value)
            else:
                raise ValueError(f"不支持的节点元数据键: '{key}'")

        return meta

    def _split_meta_pairs(self, text: str) -> List[str]:
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
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
                continue

            if char in ('"', "'"):
                quote = char
                buffer.append(char)
                continue

            if char in "([{" :
                depth += 1
                buffer.append(char)
                continue

            if char in ")]}":
                depth = max(0, depth - 1)
                buffer.append(char)
                continue

            if char == "," and depth == 0:
                result.append("".join(buffer).strip())
                buffer = []
                continue

            buffer.append(char)

        if quote is not None:
            raise ValueError("节点元数据引号未闭合")

        tail = "".join(buffer).strip()
        if tail:
            result.append(tail)
        return result

    def _parse_meta_value(self, raw: str) -> Any:
        lowered = raw.lower()
        if lowered in ("true", "yes", "on"):
            return True
        if lowered in ("false", "no", "off"):
            return False
        if raw == "1":
            return True
        if raw == "0":
            return False

        try:
            return ast.literal_eval(raw)
        except Exception:
            return raw

    def _to_bool(self, value: Any, field_name: str) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in ("true", "1", "yes", "on"):
                return True
            if lowered in ("false", "0", "no", "off"):
                return False
        raise ValueError(f"节点元数据字段 '{field_name}' 期望布尔值，实际为: {value}")

    def _parse_python_node_block(
        self,
        code_block: str,
        line_number: int,
        fallback_name: Optional[str],
        is_async: bool,
        disabled: bool,
        description: str,
    ) -> Statement:
        normalized_block = self._strip_non_meta_comments(code_block)
        try:
            tree = ast.parse(normalized_block)
        except SyntaxError as e:
            raise ValueError(f"节点代码语法错误: {e}")

        if len(tree.body) != 1:
            raise ValueError("每个节点块必须且只能包含一条语句（建议使用单条赋值语句）")

        node = tree.body[0]
        variable: Optional[str] = None
        call_node: Optional[ast.Call] = None

        if isinstance(node, ast.Assign):
            if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                raise ValueError("节点赋值语句必须是简单变量赋值，如 a = Logic.Expression(...)")
            variable = node.targets[0].id
            if not isinstance(node.value, ast.Call):
                raise ValueError("节点赋值右侧必须是节点调用，如 Logic.Expression(...)")
            call_node = node.value
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            if not fallback_name:
                raise ValueError("节点块为无赋值调用时，需在 #@node(...) 中提供 name=... 元数据")
            variable = fallback_name
            call_node = node.value
        else:
            raise ValueError("节点块只支持调用表达式或赋值调用表达式")

        call_expr = ast.unparse(call_node)
        node_type, config = self._parse_node_call(call_expr)
        depends_on = self._extract_dependencies(call_expr, node_type)

        stmt = Statement(
            line_number=line_number,
            variable=variable,
            node_type=node_type,
            config=config,
            is_async=is_async,
            depends_on=depends_on,
            code=call_expr,
            disabled=disabled,
            description=description,
        )

        logger.debug(
            f"[WorkflowParser/Marker] 节点: {variable}, 类型: {node_type}, "
            f"async: {is_async}, disabled: {disabled}, description: {description}"
        )
        return stmt

    def _strip_non_meta_comments(self, code_block: str) -> str:
        kept_lines: List[str] = []
        for raw_line in code_block.splitlines():
            stripped = raw_line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                continue
            kept_lines.append(raw_line)
        return "\n".join(kept_lines).strip()

    def _parse_node_call(self, call_expr: str) -> Tuple[str, Dict[str, Any]]:
        try:
            tree = ast.parse(call_expr, mode="eval")
            expr = tree.body

            if not isinstance(expr, ast.Call):
                raise ValueError("不是有效的节点调用")

            if isinstance(expr.func, ast.Attribute):
                if isinstance(expr.func.value, ast.Name):
                    category = expr.func.value.id
                    method = expr.func.attr
                    node_type = f"{category}.{method}"
                elif isinstance(expr.func.value, ast.Attribute):
                    parts = []
                    node = expr.func
                    while isinstance(node, ast.Attribute):
                        parts.insert(0, node.attr)
                        node = node.value
                    if isinstance(node, ast.Name):
                        parts.insert(0, node.id)
                    node_type = ".".join(parts)
                else:
                    raise ValueError("不支持的节点类型格式")
            else:
                raise ValueError("节点调用必须是 NodeType.Method(...) 格式")

            config = {}
            for keyword in expr.keywords:
                key = keyword.arg
                value = self._parse_value(keyword.value)
                config[key] = value

            return node_type, config
        except SyntaxError as e:
            raise ValueError(f"语法错误: {e}")
        except Exception as e:
            raise ValueError(f"解析失败: {e}")

    def _parse_value(self, node: ast.AST) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return f"${node.id}"
        if isinstance(node, ast.Attribute):
            obj = self._parse_value(node.value)
            return f"{obj}.{node.attr}"
        if isinstance(node, ast.List):
            return [self._parse_value(elt) for elt in node.elts]
        if isinstance(node, ast.Dict):
            return {self._parse_value(k): self._parse_value(v) for k, v in zip(node.keys, node.values)}
        if isinstance(node, (ast.ListComp, ast.DictComp)):
            return f"${{{ast.unparse(node)}}}"
        return f"${{{ast.unparse(node)}}}"

    def _extract_dependencies(self, expr: str, exclude_node_type: Optional[str] = None) -> List[str]:
        try:
            tree = ast.parse(expr, mode="eval")
        except Exception:
            return []

        dependencies = set()
        exclude_parts = set(exclude_node_type.split(".")) if exclude_node_type else set()
        safe_names = get_safe_global_names()

        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                if (
                    node.id not in ["True", "False", "None"]
                    and node.id not in exclude_parts
                    and node.id not in safe_names
                ):
                    dependencies.add(node.id)
            elif isinstance(node, ast.Attribute):
                root = node
                while isinstance(root, ast.Attribute):
                    root = root.value
                if (
                    isinstance(root, ast.Name)
                    and root.id not in exclude_parts
                    and root.id not in safe_names
                ):
                    dependencies.add(root.id)

        return sorted(list(dependencies))


def parse_workflow(code: str) -> ExecutionPlan:
    """便捷函数：解析工作流代码。"""
    parser = WorkflowParser()
    return parser.parse(code)
