from typing import Any, Dict
from pydantic import Field
from loguru import logger

from ...registry import register_node
from ...types import ExecutionResult, NodePort
from ..base import BaseNode, BaseNodeConfig


class LogicLogConfig(BaseNodeConfig):
    message: str = Field("", description="日志消息模板")
    level: str = Field("info", description="日志级别", pattern="^(debug|info|warn|error)$")
    include_input: bool = Field(True, description="是否包含输入数据")


@register_node
class LogicLogNode(BaseNode):
    node_type = "Logic.Log"
    category = "logic"
    label = "日志输出"
    description = "输出日志信息，用于调试"
    config_model = LogicLogConfig

    @classmethod
    def get_ports(cls):
        return {
            "inputs": [NodePort("input", "any", description="要记录的数据")],
            "outputs": [NodePort("output", "any", description="透传输入数据")]
        }

    async def execute(self, inputs: Dict[str, Any], config: LogicLogConfig) -> ExecutionResult:
        """日志节点 - 输出调试信息"""
        input_data = inputs.get("input")
        
        # 构建日志消息
        log_parts = []
        if config.message:
            log_parts.append(config.message)
        if config.include_input:
            log_parts.append(f"数据: {input_data}")
        
        log_message = " | ".join(log_parts) if log_parts else str(input_data)
        
        # 根据级别输出日志
        level = config.level.lower()
        if level == "debug":
            logger.debug(f"[Log节点] {log_message}")
        elif level == "info":
            logger.info(f"[Log节点] {log_message}")
        elif level == "warn":
            logger.warning(f"[Log节点] {log_message}")
        elif level == "error":
            logger.error(f"[Log节点] {log_message}")
        
        # 创建执行结果并添加日志
        result = ExecutionResult(
            success=True,
            outputs={"output": input_data}
        )
        result.add_log(level, log_message)
        
        return result
