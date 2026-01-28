from typing import Any, Dict, Optional
from loguru import logger
from pydantic import Field

from ...registry import register_node
from ...types import ExecutionResult, NodePort
from ..base import BaseNode, BaseNodeConfig


class GenerateRangeConfig(BaseNodeConfig):
    """生成序列节点配置"""
    start: int = Field(1, description="起始值")
    count_source: str = Field(..., description="数量来源路径，如 content.volume_count")
    output_field: str = Field("index", description="输出字段名")
    extra_fields: Optional[Dict[str, str]] = Field(default_factory=dict, description="附加字段映射，key为字段名，value为路径")


@register_node
class GenerateRangeNode(BaseNode):
    """生成序列节点
    
    用于生成数字序列，常用于批量创建卡片。
    替代 Data.Transform 中的 range() 表达式。
    """
    node_type = "Data.GenerateRange"
    category = "data"
    label = "生成序列"
    description = "生成数字序列，用于批量操作"
    config_model = GenerateRangeConfig

    @classmethod
    def get_ports(cls):
        return {
            "inputs": [
                NodePort("input", "any", required=True, description="输入数据源（用于提取count）")
            ],
            "outputs": [
                NodePort("output", "list", description="生成的序列列表")
            ]
        }

    async def execute(self, inputs: Dict[str, Any], config: GenerateRangeConfig) -> ExecutionResult:
        """执行序列生成"""
        input_data = inputs.get("input")
        
        if not input_data:
            return ExecutionResult(success=False, error="缺少输入数据")
        
        # 1. 提取 count
        count = self._extract_value(input_data, config.count_source)
        if count is None:
            return ExecutionResult(success=False, error=f"无法从路径 {config.count_source} 提取数量")
        
        try:
            count = int(count)
        except (ValueError, TypeError):
            return ExecutionResult(success=False, error=f"数量值无效: {count}")
        
        if count < 0:
            return ExecutionResult(success=False, error=f"数量不能为负数: {count}")
        
        # 2. 生成序列
        result_list = []
        for i in range(count):
            item = {config.output_field: config.start + i}
            
            # 3. 添加额外字段
            if config.extra_fields:
                for field_name, source_path in config.extra_fields.items():
                    value = self._extract_value(input_data, source_path)
                    if value is not None:
                        item[field_name] = value
            
            result_list.append(item)
        
        logger.info(f"[GenerateRange] 生成了 {len(result_list)} 个项目")
        
        return ExecutionResult(
            success=True,
            outputs={"output": result_list}
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
