import asyncio
from typing import Any, Dict
from pydantic import Field
from loguru import logger

from ...registry import register_node
from ...types import ExecutionResult, NodePort
from ..base import BaseNode, BaseNodeConfig


class LogicDelayConfig(BaseNodeConfig):
    seconds: float = Field(1.0, description="延迟秒数")


@register_node
class LogicDelayNode(BaseNode):
    node_type = "Logic.Delay"
    category = "logic"
    label = "延迟"
    description = "延迟指定时间后继续"
    config_model = LogicDelayConfig

    @classmethod
    def get_ports(cls):
        return {
            "inputs": [NodePort("input", "any")],
            "outputs": [NodePort("output", "any")]
        }

    async def execute(self, inputs: Dict[str, Any], config: LogicDelayConfig) -> ExecutionResult:
        """延迟节点"""
        input_data = inputs.get("input")
        
        logger.info(f"[Delay] 延迟 {config.seconds} 秒")
        await asyncio.sleep(config.seconds)
        
        return ExecutionResult(
            success=True,
            outputs={"output": input_data}
        )
