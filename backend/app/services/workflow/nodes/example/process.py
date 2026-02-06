"""示例节点 - 展示新的 BaseNode 接口使用

包含进度推送和流式执行的示例。
"""

from typing import List, Dict, Any, AsyncIterator, Union, TYPE_CHECKING
from pydantic import BaseModel, Field
from loguru import logger
import asyncio

if TYPE_CHECKING:
    from ...engine.async_executor import ProgressEvent

from ..base import BaseNode
from ...registry import register_node


# ============= Example.Process 节点 =============

class ExampleProcessInput(BaseModel):
    """示例处理节点输入"""
    items: List[str] = Field(..., description="要处理的项目列表")
    delay: float = Field(0.5, description="每项处理延迟(秒)", ge=0.0, le=10.0)
    enable_progress: bool = Field(True, description="是否启用进度推送")


class ExampleProcessOutput(BaseModel):
    """示例处理节点输出"""
    results: List[Dict[str, Any]] = Field(..., description="处理结果列表")
    summary: Dict[str, Any] = Field(..., description="处理摘要")


@register_node
class ExampleProcessNode(BaseNode[ExampleProcessInput, ExampleProcessOutput]):
    """示例处理节点

    展示如何使用新的 BaseNode 接口：
    1. 使用 Pydantic 输入输出模型
    2. 实现流式执行和进度推送
    3. 类型安全的输入输出
    """

    node_type = "Example.Process"
    category = "example"
    label = "示例处理"
    description = "处理项目列表并推送进度（用于测试和演示）"

    input_model = ExampleProcessInput
    output_model = ExampleProcessOutput

    async def execute(self, inputs: ExampleProcessInput) -> AsyncIterator[Union['ProgressEvent', ExampleProcessOutput]]:
        """流式执行方法（支持进度推送和断点续传）
        
        断点续传机制：
        1. 从 self.context.checkpoint 读取上次的进度
        2. 从中断位置继续处理
        3. 每次进度更新时保存检查点数据
        """
        from ...engine.async_executor import ProgressEvent
        
        logger.info(f"[Example.Process] 开始处理 {len(inputs.items)} 个项目")

        # === 1. 读取检查点（自动注入）===
        checkpoint = getattr(self.context, 'checkpoint', None)
        start_index = checkpoint.get('processed_count', 0) if checkpoint else 0
        
        if start_index > 0:
            logger.info(f"[Example.Process] 从检查点恢复: 已处理 {start_index}/{len(inputs.items)}")

        results = []
        total = len(inputs.items)
        
        # === 2. 从检查点继续处理 ===
        for i in range(start_index, total):
            item = inputs.items[i]
            
            # 模拟处理
            await asyncio.sleep(inputs.delay)
            result = {"item": item, "processed": True, "index": i}
            results.append(result)
            
            # === 3. 报告进度（自动保存检查点）===
            if inputs.enable_progress:
                percent = ((i + 1) / total) * 100
                yield ProgressEvent(
                    percent=percent,
                    message=f"正在处理: {item} ({i+1}/{total})",
                    data={
                        'processed_count': i + 1,  # ✅ 轻量级：计数器
                        'last_item': item          # ✅ 轻量级：标识符
                    }
                )

        summary = {
            "total": len(inputs.items),
            "processed": len(results),
            "success_rate": 1.0
        }

        logger.info(f"[Example.Process] 处理完成: {summary}")

        # === 4. 返回最终结果 ===
        yield ExampleProcessOutput(
            results=results,
            summary=summary
        )

class BatchProcessInput(BaseModel):
    """批量处理节点输入"""
    data: List[Any] = Field(..., description="要处理的数据列表")
    batch_size: int = Field(10, description="批次大小", ge=1, le=100)
    parallel: bool = Field(False, description="是否并行处理批次")


class BatchProcessOutput(BaseModel):
    """批量处理节点输出"""
    results: List[Dict[str, Any]] = Field(..., description="处理结果列表")
    total_processed: int = Field(..., description="处理的总数")


@register_node
class BatchProcessNode(BaseNode[BatchProcessInput, BatchProcessOutput]):
    """批量处理节点

    展示批量处理和并行执行。
    """

    node_type = "Example.BatchProcess"
    category = "example"
    label = "批量处理"
    description = "批量处理数据，支持并行（用于测试和演示）"

    input_model = BatchProcessInput
    output_model = BatchProcessOutput

    async def execute(self, inputs: BatchProcessInput) -> AsyncIterator[BatchProcessOutput]:
        """批量处理执行"""
        logger.info(f"[Example.BatchProcess] 处理 {len(inputs.data)} 条数据，批次大小: {inputs.batch_size}")

        results = []

        # 分批处理
        for i in range(0, len(inputs.data), inputs.batch_size):
            batch = inputs.data[i:i + inputs.batch_size]

            if inputs.parallel:
                # 并行处理批次
                tasks = [self._process_item(item) for item in batch]
                batch_results = await asyncio.gather(*tasks)
            else:
                # 串行处理批次
                batch_results = []
                for item in batch:
                    result = await self._process_item(item)
                    batch_results.append(result)

            results.extend(batch_results)

        logger.info(f"[Example.BatchProcess] 处理完成: {len(results)} 条结果")

        yield BatchProcessOutput(
            results=results,
            total_processed=len(results)
        )

    async def _process_item(self, item: Any) -> Dict[str, Any]:
        """处理单个项目"""
        await asyncio.sleep(0.1)  # 模拟处理
        return {"item": item, "processed": True}
