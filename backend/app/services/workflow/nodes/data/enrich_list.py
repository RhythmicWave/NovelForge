from typing import Any, Dict
from loguru import logger
from pydantic import Field

from ...registry import register_node
from ...types import ExecutionResult, NodePort
from ..base import BaseNode, BaseNodeConfig


class EnrichListConfig(BaseNodeConfig):
    """列表富化节点配置"""
    extra_fields: Dict[str, str] = Field(default_factory=dict, description="附加字段映射，key为字段名，value为源路径")


@register_node
class EnrichListNode(BaseNode):
    """列表富化节点
    
    为列表中的每个项目添加额外字段（从上下文中提取）。
    替代 Data.Transform 中的列表推导式富化。
    """
    node_type = "Data.EnrichList"
    category = "data"
    label = "列表富化"
    description = "为列表项添加上下文字段"
    config_model = EnrichListConfig

    @classmethod
    def get_ports(cls):
        return {
            "inputs": [
                NodePort("list", "list", required=True, description="要富化的列表"),
                NodePort("context", "any", required=False, description="上下文数据源（用于提取额外字段）")
            ],
            "outputs": [
                NodePort("output", "list", description="富化后的列表")
            ]
        }

    async def execute(self, inputs: Dict[str, Any], config: EnrichListConfig) -> ExecutionResult:
        """执行列表富化"""
        input_list = inputs.get("list")
        context = inputs.get("context")
        
        if not isinstance(input_list, list):
            return ExecutionResult(success=False, error="输入必须是列表")
        
        if not config.extra_fields:
            # 没有配置额外字段，直接返回原列表
            return ExecutionResult(success=True, outputs={"output": input_list})
        
        if not context:
            return ExecutionResult(success=False, error="需要上下文数据来提取额外字段")
        
        # 富化列表
        enriched_list = []
        for item in input_list:
            # 复制原项目
            if isinstance(item, dict):
                enriched_item = dict(item)
            else:
                # 如果不是字典，包装成字典
                enriched_item = {"value": item}
            
            # 添加额外字段
            for field_name, source_path in config.extra_fields.items():
                value = self._extract_value(context, source_path)
                if value is not None:
                    enriched_item[field_name] = value
            
            enriched_list.append(enriched_item)
        
        logger.info(f"[EnrichList] 富化了 {len(enriched_list)} 个项目，添加了 {len(config.extra_fields)} 个字段")
        
        return ExecutionResult(
            success=True,
            outputs={"output": enriched_list}
        )
    
    def _extract_value(self, data: Any, path: str) -> Any:
        """从数据中提取值"""
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
