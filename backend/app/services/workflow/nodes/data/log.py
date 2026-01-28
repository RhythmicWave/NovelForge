from typing import Any, Dict
from pydantic import Field
from loguru import logger

from ...registry import register_node
from ...types import ExecutionResult, NodePort
from ..base import BaseNode, BaseNodeConfig


class DataLogConfig(BaseNodeConfig):
    message: str = Field("", description="日志消息")
    level: str = Field("info", description="日志级别", pattern="^(debug|info|warn|error)$")


@register_node
class DataLogNode(BaseNode):
    node_type = "Data.Log"
    category = "data"
    label = "日志输出"
    description = "输出日志信息"
    config_model = DataLogConfig

    @classmethod
    def get_ports(cls):
        return {
            "inputs": [NodePort("data", "any", description="要记录的数据")],
            "outputs": [NodePort("output", "any", description="原样输出")]
        }

    async def execute(self, inputs: Dict[str, Any], config: DataLogConfig) -> ExecutionResult:
        """日志输出节点"""
        # 兼容 data 和 input 两种端口名 (如果上游连接错)
        data = inputs.get("data")
        if data is None:
             data = inputs.get("input")
             
        log_message = f"[Workflow Log] {config.message}: {data}"
        
        level = config.level.lower()
        if level == "debug":
            logger.debug(log_message)
        elif level == "info":
            logger.info(log_message)
        elif level == "warn":
            logger.warning(log_message)
        elif level == "error":
            logger.error(log_message)
        
        # 输出包含消息和数据的对象，方便下游节点使用
        output_data = {
            "message": config.message,
            "data": data,
            "level": level,
            "log": log_message
        }
        
        result = ExecutionResult(
            success=True,
            outputs={"output": output_data}
        )
        result.add_log(level, config.message, data=data)
        
        return result
