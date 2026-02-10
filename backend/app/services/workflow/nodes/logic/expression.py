"""表达式节点 - 数据转换与提取"""

from __future__ import annotations

import inspect
from typing import Any, AsyncIterator

from pydantic import BaseModel, Field

from app.services.workflow.expressions import evaluate_expression
from app.services.workflow.expressions.builtins import get_safe_builtins
from app.services.workflow.expressions.functions import get_builtin_functions, get_helper_metadata
from app.services.workflow.nodes.base import BaseNode
from app.services.workflow.registry import register_node


class ExpressionInput(BaseModel):
    """表达式节点输入"""

    expression: str = Field(
        ...,
        description="Python 表达式（可以访问所有已定义变量）",
        json_schema_extra={
            "x-component": "CodeEditor",
            "x-component-props": {
                "language": "python",
                "placeholder": "例如：card.content.field or []\n[item.name for item in items if item.name]"
            }
        },
    )


class ExpressionOutput(BaseModel):
    """表达式节点输出"""

    result: Any = Field(..., description="表达式计算结果")


def _build_helper_docs() -> list[str]:
    helpers = get_builtin_functions()
    helper_meta = get_helper_metadata()
    if not helpers:
        return ["- （无业务 helper）"]

    ranked_names = sorted(
        helpers.keys(),
        key=lambda name: (helper_meta.get(name).priority if helper_meta.get(name) else 50, name),
        reverse=True,
    )

    lines: list[str] = ["### 推荐 helper（按优先级）"]
    for name in ranked_names[:3]:
        func = helpers[name]
        signature = str(inspect.signature(func))
        meta = helper_meta.get(name)
        summary = (meta.summary if meta else ((inspect.getdoc(func) or "").splitlines()[0] if inspect.getdoc(func) else "业务辅助函数")).strip()
        scenario = meta.scenario if meta else "通用"
        example = meta.example if meta else ""
        line = f"- `{name}{signature}`（场景：{scenario}，优先级：{meta.priority if meta else 50}）\n  - 说明：{summary}"
        if example:
            line += f"\n  - 示例：`{example}`"
        lines.append(line)

    lines.append("\n### 全量 helper 列表")
    for name in ranked_names:
        func = helpers[name]
        signature = str(inspect.signature(func))
        meta = helper_meta.get(name)
        summary = (meta.summary if meta else ((inspect.getdoc(func) or "").splitlines()[0] if inspect.getdoc(func) else "业务辅助函数")).strip()
        lines.append(f"- `{name}{signature}`：{summary}")
    return lines


def _build_builtin_docs() -> str:
    builtin_names = sorted(get_safe_builtins().keys())
    return ", ".join(f"`{name}`" for name in builtin_names)


def _build_expression_documentation() -> str:
    helper_lines = "\n".join(_build_helper_docs())
    builtin_line = _build_builtin_docs()

    return f"""
表达式节点用于执行**受控 Python 表达式**，适合做字段提取、列表转换、条件拼装。

## 核心规则（AI 必读）
1. 节点输出结构固定为 `{{"result": <计算结果>}}`，后续节点必须通过 `.result` 访问。
2. 可直接访问工作流上下文变量（如 `project`、`cards`、`wait_xxx`）。
3. 推荐优先使用标准 Python 表达式语法（推导式、三元表达式、f-string）。
4. 字典支持点号访问（如 `card.content.title`），缺失字段会按空值处理。

## 推荐写法
```python
card.content.items or []
[item for item in items if item.status == "active"]
f"共处理 {{len(items)}} 项"
items if wait_ai.count > 0 else []
```

## 输出访问示例
```python
mapped = Logic.Expression(expression="{{item.id: item.name for item in cards}}")
Card.BatchUpsert(items=mapped.result)
```

## 可用 Python 内置函数
{builtin_line}

## 业务 helper（自动生成）
{helper_lines}
""".strip()


@register_node
class ExpressionNode(BaseNode):
    """表达式节点（受控 Python eval）"""

    node_type = "Logic.Expression"
    category = "logic"
    label = "表达式计算"
    description = "执行受控 Python 表达式，输出 result"

    input_model = ExpressionInput
    output_model = ExpressionOutput

    @classmethod
    def get_metadata(cls):
        metadata = super().get_metadata()
        metadata.description = cls.description
        metadata.documentation = _build_expression_documentation()
        return metadata

    async def execute(self, input_data: ExpressionInput) -> AsyncIterator[ExpressionOutput]:
        """执行表达式"""
        expr_context = self.context.variables

        try:
            result = evaluate_expression(input_data.expression, expr_context)
            yield ExpressionOutput(result=result)
        except Exception as e:
            raise ValueError(
                f"表达式执行失败: {str(e)}\n"
                f"表达式: {input_data.expression}\n"
                f"可用变量: {', '.join(expr_context.keys())}"
            )
