import asyncio
from typing import Any, AsyncIterator
from pydantic import BaseModel, Field
from loguru import logger

from ...registry import register_node
from ..base import BaseNode


class LogicDelayInput(BaseModel):
    """延迟输入"""
    input: Any = Field(None, description="输入数据（透传）")
    seconds: float = Field(1.0, description="延迟秒数")


class LogicDelayOutput(BaseModel):
    """延迟输出"""
    output: Any = Field(None, description="输出数据（透传）")


@register_node
class LogicDelayNode(BaseNode[LogicDelayInput, LogicDelayOutput]):
    node_type = "Logic.Delay"
    category = "logic"
    label = "延迟"
    description = "延迟指定时间后继续"
    
    input_model = LogicDelayInput
    output_model = LogicDelayOutput

    async def execute(self, inputs: LogicDelayInput) -> AsyncIterator[LogicDelayOutput]:
        """延迟节点"""
        logger.info(f"[Delay] 延迟 {inputs.seconds} 秒")
        await asyncio.sleep(inputs.seconds)
        
        yield LogicDelayOutput(output=inputs.input)
