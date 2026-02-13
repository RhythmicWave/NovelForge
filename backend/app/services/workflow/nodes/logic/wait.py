"""Logic.Wait 节点 - 等待异步任务完成"""

from typing import Any, List, Union, AsyncIterator
from pydantic import BaseModel, Field, field_validator

from ...registry import register_node
from ..base import BaseNode


class WaitInput(BaseModel):
    """Wait 节点输入"""
    input: Any = Field(None, description="输入数据（透传）")
    tasks: Union[str, List[str]] = Field(
        ...,
        description="要等待的异步任务变量名（单个或列表）",
        json_schema_extra={
            "x-component": "TaskSelect",
            "x-multiple": True
        }
    )
    
    @field_validator('tasks', mode='before')
    @classmethod
    def normalize_tasks(cls, v):
        """将单个任务转换为列表"""
        if isinstance(v, str):
            return [v]
        return v


class WaitOutput(BaseModel):
    """Wait 节点输出"""
    waited_tasks: List[str] = Field(..., description="已等待的任务列表")
    count: int = Field(..., description="等待的任务数量")


@register_node
class WaitNode(BaseNode[WaitInput, WaitOutput]):
    """等待异步任务完成
    
    用于等待一个或多个异步任务完成后再继续执行。
    
    示例：
        wait_result = Logic.Wait(tasks=["task_a", "task_b"])
    """
    
    node_type = "Logic.Wait"
    category = "logic"
    label = "等待任务"
    description = "等待一个或多个异步任务完成"
    
    input_model = WaitInput
    output_model = WaitOutput
    
    async def execute(self, inputs: WaitInput) -> AsyncIterator[WaitOutput]:
        """执行等待
        
        注意：实际的等待逻辑在 AsyncExecutor 中处理，
        这里只是返回一个占位结果。
        """
        yield WaitOutput(
            waited_tasks=inputs.tasks,
            count=len(inputs.tasks)
        )
