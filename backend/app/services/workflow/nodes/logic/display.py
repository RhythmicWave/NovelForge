import json
from typing import Any, Dict
from pydantic import Field
from loguru import logger

from ...registry import register_node
from ...types import ExecutionResult, NodePort
from ..base import BaseNode, BaseNodeConfig


class LogicDisplayConfig(BaseNodeConfig):
    title: str = Field("输出预览", description="显示标题")
    format: str = Field("auto", description="显示格式", pattern="^(auto|json|text)$")


@register_node
class LogicDisplayNode(BaseNode):
    node_type = "Logic.Display"
    category = "logic"
    label = "显示输出"
    description = "显示节点输出内容（用于预览和调试）"
    config_model = LogicDisplayConfig

    @classmethod
    def get_ports(cls):
        return {
            "inputs": [NodePort("input", "any", description="要显示的数据")],
            "outputs": [NodePort("output", "any", description="透传数据")]
        }

    async def execute(self, inputs: Dict[str, Any], config: LogicDisplayConfig) -> ExecutionResult:
        """显示输出节点
        
        将输入数据格式化并保存到 outputs_json 中，供前端展示
        """
        input_data = inputs.get("input")
        
        # 格式化数据
        try:
            if config.format == "json" or (config.format == "auto" and isinstance(input_data, (dict, list))):
                # JSON 格式
                formatted_data = json.dumps(input_data, ensure_ascii=False, indent=2)
                display_type = "json"
            else:
                # 文本格式
                formatted_data = str(input_data) if input_data is not None else ""
                display_type = "text"
            
            logger.info(f"[Display] {config.title}: {formatted_data[:100]}...")
            
            return ExecutionResult(
                success=True,
                outputs={
                    "output": input_data,  # 透传原始数据
                    "display": {
                        "title": config.title,
                        "type": display_type,
                        "content": formatted_data,
                        "raw_data": input_data
                    }
                }
            )
        except Exception as e:
            logger.error(f"[Display] 格式化失败: {e}")
            return ExecutionResult(
                success=False,
                error=f"格式化失败: {str(e)}"
            )
