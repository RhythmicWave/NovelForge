import asyncio
import os
from typing import Any, Dict, List, Optional
from loguru import logger
from pydantic import Field

from app.db.models import NodeExecutionState, WorkflowRun
from app.services.ai.core.llm_service import build_chat_model, generate_structured
from ...registry import register_node
from ...types import ExecutionResult, NodePort, NodeStatus
from ..base import BaseNode, BaseNodeConfig


class BatchStructuredConfig(BaseNodeConfig):
    llm_config_id: int = Field(..., description="LLM 配置 ID", json_schema_extra={"x-component": "LLMSelect"})
    prompt_template: Optional[str] = Field(None, description="提示词模板，支持 {{content}} 和 {{item.field}}", json_schema_extra={"x-component": "Textarea"})
    response_model_id: str = Field(..., description="响应模型 (CardType或内置)", json_schema_extra={"x-component": "ResponseModelSelect"})
    concurrency: int = Field(5, description="最大并发数", ge=1, le=20)
    max_retries: int = Field(3, description="最大重试次数")
    cache_key: Optional[str] = Field(None, description="缓存Key (用于断点续传)，若为空则使用 item.path 或 index")


@register_node
class BatchStructuredNode(BaseNode):
    node_type = "AI.BatchStructured"
    category = "ai"
    label = "批量结构化生成"
    description = "批量调用 LLM 进行结构化提取，支持并发和断点续传"
    config_model = BatchStructuredConfig

    @classmethod
    def get_ports(cls):
        return {
            "inputs": [
                NodePort("items", "list", required=True, description="数据列表 (包含元数据)"),
                NodePort("prompt_template", "string", required=False, description="提示词模板 (覆盖配置)")
            ],
            "outputs": [
                NodePort("results", "list", description="提取结果列表"),
                NodePort("errors", "list", description="错误项列表")
            ]
        }

    async def execute(self, inputs: Dict[str, Any], config: BatchStructuredConfig) -> ExecutionResult:
        items = inputs.get("items", [])
        if not isinstance(items, list):
            return ExecutionResult(success=False, error="输入 items 必须是列表")

        if not items:
            return ExecutionResult(success=True, outputs={"results": [], "errors": []})

        prompt_template = inputs.get("prompt_template") or config.prompt_template
        if not prompt_template:
             return ExecutionResult(success=False, error="提示词模板为空")

        # 并发控制

        semaphore = asyncio.Semaphore(config.concurrency)
        results = [None] * len(items) # 保持顺序
        errors = []
        
        total = len(items)
        processed_count = 0
        
        async def process_item(index, item):
            nonlocal processed_count
            async with semaphore:
                try:
                    # 1. 准备内容 (Pass-by-Reference)
                    content = ""
                    path = item.get("path")
                    logger.info(f"[BatchStructured] Item {index}: Checking path={path}")
                    
                    if path and os.path.exists(path):
                        try:
                            # 异步读取文件？这里直接同步读对于小文件还可以，大文件可能会阻塞 loop
                            # 最好用 aiofiles
                            with open(path, "r", encoding="utf-8") as f:
                                content = f.read()
                            logger.info(f"[BatchStructured] Item {index}: Successfully read {len(content)} characters from file")
                        except Exception as e:
                            logger.error(f"读取文件失败: {path}, {e}")
                            content = f"[读取失败: {e}]"
                    else:
                        logger.warning(f"[BatchStructured] Item {index}: Path not found or doesn't exist: {path}")
                    
                    if not content and "content" in item:
                        content = item["content"]
                        logger.info(f"[BatchStructured] Item {index}: Using content from item dict, length={len(content)}")
                    
                    # Debug logging
                    logger.info(f"[BatchStructured] Item {index}: path={path}, content_length={len(content)}")

                    # 2. 渲染 Prompt
                    # 支持 {{content}} 和 {{item.field}}
                    # 简单替换
                    current_prompt = prompt_template.replace("{{content}}", str(content))
                    # 替换 item 字段
                    for k, v in item.items():
                        if k != "content": # 避免重复打印大内容
                             current_prompt = current_prompt.replace(f"{{{{item.{k}}}}}", str(v))
                    
                    # Debug: log first 200 chars of prompt
                    logger.info(f"[BatchStructured] Prompt preview (item {index}): {current_prompt[:200]}...")
                    
                    # 3. LLM 调用
                    # schema 自动处理 logic
                    from .structured import StructuredGenerateNode
                    # 复用逻辑 (这有点 tricky，最好的方式是抽离 schema 获取逻辑)
                    # 暂时这里再写一遍，或者依赖 llm_service 的 generate_structured
                    

                    
                    # 构造 Schema
                    # 注意：generate_structured 需要 Pydantic 模型或 Schema 字典
                    # 我们从 CardType 获取
                    from app.services.workflow.nodes.ai.structured import StructuredGenerateNode
                    # _get_schema 是实例方法，需要传 self (虽然未使用)，且第二个参数是 config (需包含 response_model_id)
                    schema = StructuredGenerateNode._get_schema(self, self.context.session, config)

                    llm_result = await generate_structured(
                        session=self.context.session,
                        llm_config_id=config.llm_config_id,
                        user_prompt=current_prompt,
                        output_type=schema, # 这里虽然签名是 Type[BaseModel]，但内部 LangChain 支持 schema dict
                        max_retries=config.max_retries
                    )
                    
                    # 结果
                    result_data = llm_result # 应该是 dict
                    # 合并原始 meta (可选)
                    # output -> { ...result, ...item_meta }
                    # 最好保留 original item context
                    final_result = {
                        "ai_result": result_data,
                        "meta": item
                    }
                    results[index] = final_result
                    
                except Exception as e:
                    logger.error(f"Batch Item {index} failed: {e}")
                    errors.append({"index": index, "item": item, "error": str(e)})
                    results[index] = {"error": str(e), "meta": item} # 占位
                
                finally:
                    processed_count += 1
        
        # 创建 Tasks
        tasks = [process_item(i, item) for i, item in enumerate(items)]
        await asyncio.gather(*tasks)
        
        return ExecutionResult(
            success=True,
            outputs={
                "results": [r for r in results if r is not None],
                "errors": errors
            }
        )
