"""表达式节点 - 数据转换和提取"""

from typing import Any, AsyncIterator
from pydantic import BaseModel, Field

from app.services.workflow.nodes.base import BaseNode
from app.services.workflow.registry import register_node
from app.services.workflow.expressions import evaluate_expression


class ExpressionInput(BaseModel):
    """表达式节点输入"""
    expression: str = Field(
        ..., 
        description="Python 表达式（可以访问所有已定义的变量）",
        json_schema_extra={
            "x-component": "CodeEditor",
            "x-component-props": {
                "language": "python",
                "placeholder": "输入 Python 表达式，例如：\ncard.content.field or []\n[item.name for item in items]"
            }
        }
    )


class ExpressionOutput(BaseModel):
    """表达式节点输出"""
    result: Any = Field(..., description="表达式计算结果")


@register_node
class ExpressionNode(BaseNode):
    """表达式节点 - 数据转换和提取
    
    用于对工作流变量执行 Python 表达式求值，支持数据提取、转换、过滤等操作。
    
    ## ⚠️ 重要：输出结构
    
    Expression 节点的输出是一个字典：`{'result': 计算结果}`
    
    **在工作流中使用时，必须通过 `.result` 访问计算结果：**
    
    ```python
    # ✅ 正确：使用 .result 访问
    items = Logic.Expression(expression="card.content.items or []")
    Card.BatchUpsert(items=items.result)  # 访问 .result
    
    # ❌ 错误：直接使用变量
    Card.BatchUpsert(items=items)  # 这会传入 {'result': [...]} 而不是列表
    ```
    
    ## 核心特性
    
    1. **访问所有变量**：可以访问工作流中所有已定义的变量
    2. **安全的属性访问**：字段不存在时返回 None，支持链式访问
    3. **字典解包**：支持 `{**dict1, **dict2}` 语法
    4. **列表推导**：支持列表推导、字典推导、条件表达式
    5. **Python 语义的 or/and**：返回实际值，不是布尔值
    
    ## 推荐用法
    
    ### 1. 优雅的属性访问 + or 默认值
    
    ```python
    # ✅ 推荐：直接访问属性，使用 or 提供默认值
    card.content.field or []
    card.content.nested.field or 0
    card.content.name or "未命名"
    
    # ⚠️ 注意：or 运算符返回第一个真值或最后一个值
    # [] or [1,2,3] → [1,2,3]  （空列表是假值）
    # None or [] → []  （None 是假值）
    # [1,2,3] or [] → [1,2,3]  （非空列表是真值）
    
    # ❌ 不推荐：使用 .get() 方法（繁琐）
    card.content.get('field', [])
    card.content.get('nested', {}).get('field', 0)
    ```
    
    ### 2. 字典解包
    
    ```python
    # ✅ 合并字典并添加新字段
    {**item, 'volume_number': stage.content.volume_number}
    
    # ✅ 合并多个字典
    {**dict1, **dict2, 'extra': 'value'}
    
    # ✅ 在列表推导中使用
    [{**item, 'parent_id': parent_map.result[item.volume]} for item in items]
    ```
    
    ### 3. 列表操作
    
    ```python
    # ✅ 提取字段
    [item.name for item in items]
    
    # ✅ 过滤
    [item for item in items if item.status == 'active']
    
    # ✅ 转换
    [{'id': item.id, 'name': item.name} for item in items]
    
    # ✅ 带默认值的提取
    [item.name or "未命名" for item in items]
    ```
    
    ### 4. 条件表达式
    
    ```python
    # ✅ 三元运算符
    items[0] if items else None
    value if value > 0 else 0
    "有数据" if items else "无数据"
    ```
    
    ### 5. 字典推导
    
    ```python
    # ✅ 创建映射
    {card.title: card.id for card in cards}
    
    # ✅ 过滤字典
    {k: v for k, v in data.items() if v is not None}
    ```
    
    ## 完整示例
    
    ```python
    # 示例 1：提取嵌套字段（记得用 .result）
    organizations = Logic.Expression(
        expression="card.content.world_view.organizations or []"
    )
    # 使用时：organizations.result
    Card.BatchUpsert(items=organizations.result)
    
    # 示例 2：列表转换
    enriched = Logic.Expression(
        expression="[{**item, 'parent_id': parent_map.result[item.volume]} for item in items]"
    )
    # 使用时：enriched.result
    Card.BatchUpsert(items=enriched.result)
    
    # 示例 3：创建映射
    volume_map = Logic.Expression(
        expression="{card.title: card.id for card in volume_cards.cards or []}"
    )
    # 使用时：volume_map.result[key]
    parent_id = volume_map.result[item.volume]
    
    # 示例 4：条件过滤
    active_items = Logic.Expression(
        expression="[item for item in items if item.status == 'active']"
    )
    # 使用时：active_items.result
    ```
    
    ## 常见陷阱
    
    ### 陷阱 1：忘记使用 .result
    
    ```python
    # ❌ 错误
    items = Logic.Expression(expression="card.content.items or []")
    Card.BatchUpsert(items=items)  # 传入的是 {'result': [...]}
    
    # ✅ 正确
    items = Logic.Expression(expression="card.content.items or []")
    Card.BatchUpsert(items=items.result)  # 传入的是 [...]
    ```
    
    ### 陷阱 2：在表达式内部访问其他 Expression 节点
    
    ```python
    # ❌ 错误：在表达式内部忘记 .result
    volume_map = Logic.Expression(expression="{...}")
    chapters = Logic.Expression(
        expression="[{**item, 'parent': volume_map[item.vol]} for item in items]"
    )
    # volume_map 是 {'result': {...}}，不能直接当字典用
    
    # ✅ 正确：在表达式内部也要用 .result
    chapters = Logic.Expression(
        expression="[{**item, 'parent': volume_map.result[item.vol]} for item in items]"
    )
    ```
    
    ### 陷阱 3：误解 or 运算符
    
    ```python
    # ⚠️ 注意：or 返回第一个真值，不是布尔值
    
    # 正确理解：
    [] or [1,2,3]  # → [1,2,3]（空列表是假值，返回第二个）
    [1,2,3] or []  # → [1,2,3]（非空列表是真值，返回第一个）
    None or "默认"  # → "默认"（None 是假值）
    0 or 42  # → 42（0 是假值）
    "" or "默认"  # → "默认"（空字符串是假值）
    
    # 如果字段可能是空列表，or 不会替换它：
    card.content.items or []  # 如果 items=[]，返回 []（不是第二个 []）
    # 因为空列表是假值，所以会返回第二个 []
    ```
    
    ## 注意事项
    
    - **输出必须通过 `.result` 访问**
    - 属性访问不存在时返回 None（不会报错）
    - 支持链式访问：`a.b.c.d`（任何一层为 None 都返回 None）
    - `or` 运算符返回第一个真值或最后一个值（不是布尔值）
    - `and` 运算符返回第一个假值或最后一个值（不是布尔值）
    - 字典访问使用 `dict[key]` 或 `dict.get(key)`
    """
    
    node_type = "Logic.Expression"
    category = "logic"
    label = "表达式计算"
    description = "对工作流变量执行 Python 表达式求值"
    
    input_model = ExpressionInput
    output_model = ExpressionOutput
    
    async def execute(self, input_data: ExpressionInput) -> AsyncIterator[ExpressionOutput]:
        """执行表达式
        
        使用工作流上下文中的所有变量作为表达式的求值环境。
        """
        # 使用整个工作流上下文作为表达式环境
        expr_context = self.context.variables
        
        # 计算表达式
        try:
            result = evaluate_expression(input_data.expression, expr_context)
            yield ExpressionOutput(result=result)
            
        except Exception as e:
            raise ValueError(
                f"表达式执行失败: {str(e)}\n"
                f"表达式: {input_data.expression}\n"
                f"可用变量: {', '.join(expr_context.keys())}"
            )
