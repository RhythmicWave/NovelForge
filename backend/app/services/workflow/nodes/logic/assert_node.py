from typing import Any, Dict, AsyncIterator
from pydantic import Field, BaseModel
from loguru import logger

from ...registry import register_node
from ..base import BaseNode
from ...expressions import evaluate_expression


class LogicAssertInput(BaseModel):
    """断言节点输入"""
    condition: str = Field(..., description="断言条件表达式")
    message: str = Field("断言失败", description="失败时的错误消息")


class LogicAssertOutput(BaseModel):
    """断言节点输出（空）"""
    pass


@register_node
class LogicAssertNode(BaseNode[LogicAssertInput, LogicAssertOutput]):
    """断言节点
    
    验证条件是否为真，如果为假则停止工作流执行。
    用于替代 Logic.End 节点，实现条件验证和提前退出。
    """
    node_type = "Logic.Assert"
    category = "logic"
    label = "断言"
    description = "验证条件，失败则停止工作流"
    
    input_model = LogicAssertInput
    output_model = LogicAssertOutput

    async def execute(self, inputs: LogicAssertInput) -> AsyncIterator[LogicAssertOutput]:
        """执行断言验证"""
        try:
            # 准备求值环境
            eval_context = {
                **self.context.variables
            }
            
            # 评估条件表达式
            result = evaluate_expression(inputs.condition, eval_context)
            is_true = bool(result)
            
            if not is_true:
                # 断言失败，抛出异常
                logger.error(f"[Assert] 断言失败: {inputs.condition} - {inputs.message}")
                raise AssertionError(f"断言失败: {inputs.message}")
            
            # 断言成功，继续执行
            logger.info(f"[Assert] 断言通过: {inputs.condition}")
            yield LogicAssertOutput()
        
        except Exception as e:
            if isinstance(e, AssertionError):
                raise
            logger.error(f"[Assert] 条件求值失败: {e}")
            raise ValueError(f"断言条件求值失败: {str(e)}")
