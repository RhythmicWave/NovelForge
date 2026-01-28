from typing import Any, Dict
from loguru import logger
from pydantic import Field

from ...registry import register_node
from ...types import ExecutionResult, NodePort
from ..base import BaseNode, BaseNodeConfig


class ExtractPathConfig(BaseNodeConfig):
    """提取路径节点配置"""
    path: str = Field(..., description="要提取的路径，如 content.character_cards")
    default_value: Any = Field(None, description="路径不存在时的默认值")


@register_node
class ExtractPathNode(BaseNode):
    """提取路径节点
    
    从输入数据中提取指定路径的值。
    替代 Data.Transform 中的简单字段访问。
    """
    node_type = "Data.ExtractPath"
    category = "data"
    label = "提取字段"
    description = "从数据中提取指定路径的值"
    config_model = ExtractPathConfig

    @classmethod
    def get_ports(cls):
        return {
            "inputs": [
                NodePort("input", "any", required=True, description="输入数据")
            ],
            "outputs": [
                NodePort("output", "any", description="提取的值")
            ]
        }

    async def execute(self, inputs: Dict[str, Any], config: ExtractPathConfig) -> ExecutionResult:
        """执行路径提取"""
        input_data = inputs.get("input")
        
        if input_data is None:
            logger.warning("[ExtractPath] 缺少输入数据")
            return ExecutionResult(success=False, error="缺少输入数据")
            
        
        # 提取值
        value = self._extract_value(input_data, config.path)
        
        # 如果提取失败且有默认值，使用默认值
        if value is None and config.default_value is not None:
            value = config.default_value
            # logger.debug(f"[ExtractPath] 路径 {config.path} 不存在，使用默认值")
        
        # logger.debug(f"[ExtractPath] 从路径 {config.path} 提取了值（类型: {type(value).__name__}）")
        
        return ExecutionResult(
            success=True,
            outputs={"output": value}
        )
    
    def _extract_value(self, data: Any, path: str) -> Any:
        """从数据中提取值
        
        支持点号路径，如 content.volume_count
        """
        if not path:
            return data
        
        parts = path.split('.')
        current = data
        
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            elif hasattr(current, part):
                current = getattr(current, part)
            else:
                return None
            
            if current is None:
                return None
        
        return current
