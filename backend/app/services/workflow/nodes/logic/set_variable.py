from typing import Any, Dict, Optional
from pydantic import Field
from loguru import logger

from ...registry import register_node
from ...types import ExecutionResult, NodePort
from ..base import BaseNode, BaseNodeConfig


class LogicSetVariableConfig(BaseNodeConfig):
    variable_name: str = Field(..., description="变量名")
    value: Optional[Any] = Field(None, description="变量值（如果没有输入连线，则使用此配置值）")


@register_node
class LogicSetVariableNode(BaseNode):
    node_type = "Logic.SetVariable"
    category = "logic"
    label = "设置变量"
    description = "设置全局变量"
    config_model = LogicSetVariableConfig

    @classmethod
    def get_ports(cls):
        return {
            "inputs": [NodePort("value", "any", description="变量值（可选，优先级高于配置）", required=False)],
            "outputs": [NodePort("output", "any")]
        }

    async def execute(self, inputs: Dict[str, Any], config: LogicSetVariableConfig) -> ExecutionResult:
        """设置变量节点"""
        # 优先使用输入端口的值，如果没有则使用配置中的值
        value = inputs.get("value")
        if value is None:
            value = config.value
        
        # 智能类型转换：尝试将字符串转换为数字或布尔值
        if isinstance(value, str):
            value_stripped = value.strip()
            # 尝试转换为整数
            try:
                value = int(value_stripped)
            except ValueError:
                # 尝试转换为浮点数
                try:
                    value = float(value_stripped)
                except ValueError:
                    # 尝试转换为布尔值
                    if value_stripped.lower() == 'true':
                        value = True
                    elif value_stripped.lower() == 'false':
                        value = False
                    # 否则保持字符串
        
        self.context.set_variable(config.variable_name, value)
        
        logger.info(f"[SetVariable] 设置变量: {config.variable_name} = {value}")
        
        return ExecutionResult(
            success=True,
            outputs={"output": value}
        )
