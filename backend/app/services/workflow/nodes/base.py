"""节点基础类和工具函数

极简类型安全设计：
1. 只有 Input 和 Output 模型，不需要 Config
2. 充分利用 Pydantic 的类型验证和 JSON Schema
3. execute 方法直接接收和返回 Pydantic 模型
4. 自动从模型生成元数据
"""

from typing import Any, Dict, Optional, List, Type, Union, AsyncIterator, Generic, TypeVar, TYPE_CHECKING
from sqlmodel import Session, select
from pydantic import BaseModel, Field
from typing_extensions import ClassVar
from abc import ABC, abstractmethod
import inspect
import asyncio

if TYPE_CHECKING:
    from ..engine.async_executor import ProgressEvent

from app.db.models import Card, CardType
from ..types import ExecutionContext, NodeMetadata


# 类型变量
TInput = TypeVar('TInput', bound=BaseModel)
TOutput = TypeVar('TOutput', bound=BaseModel)


def get_card_by_id(session: Session, card_id: int) -> Optional[Card]:
    """根据ID获取卡片"""
    return session.get(Card, card_id)


def get_card_type_by_name(session: Session, type_name: str) -> Optional[CardType]:
    """根据名称获取卡片类型"""
    stmt = select(CardType).where(CardType.name == type_name)
    return session.exec(stmt).first()


def resolve_card_reference(
    session: Session,
    reference: Any,
    context_card_id: Optional[int] = None
) -> Optional[Card]:
    """解析卡片引用

    支持的引用格式：
    - 数字：直接作为卡片ID
    - "$self": 当前上下文卡片
    - "$parent": 父卡片
    - 字典 {"id": 123}: 显式指定ID

    Args:
        session: 数据库会话
        reference: 卡片引用
        context_card_id: 上下文卡片ID（用于$self等引用）

    Returns:
        Card对象，不存在则返回None
    """
    # 数字直接作为ID
    if isinstance(reference, int):
        return get_card_by_id(session, reference)

    # 字符串引用
    if isinstance(reference, str):
        if reference == "$self" and context_card_id:
            return get_card_by_id(session, context_card_id)
        elif reference == "$parent" and context_card_id:
            card = get_card_by_id(session, context_card_id)
            if card and card.parent_id:
                return get_card_by_id(session, card.parent_id)

    # 字典引用
    if isinstance(reference, dict):
        card_id = reference.get("id")
        if card_id:
            return get_card_by_id(session, card_id)

    return None


class BaseNode(ABC, Generic[TInput, TOutput]):
    """节点基类 - 极简类型安全设计
    
    使用示例：
    ```python
    class NovelLoadInput(BaseModel):
        root_path: str = Field(..., description="小说根目录")
        file_pattern: str = Field(r".*\\.txt$", description="文件匹配")
    
    class NovelLoadOutput(BaseModel):
        chapter_list: List[Dict] = Field(..., description="章节列表")
        volume_list: List[str] = Field(..., description="分卷列表")
    
    @register_node
    class NovelLoadNode(BaseNode[NovelLoadInput, NovelLoadOutput]):
        node_type = "Novel.Load"
        category = "novel"
        label = "加载小说"
        description = "扫描小说目录"
        
        input_model = NovelLoadInput
        output_model = NovelLoadOutput
        
        async def execute(self, inputs: NovelLoadInput) -> NovelLoadOutput:
            # 直接使用类型化的输入
            chapters = scan_directory(inputs.root_path)
            
            # 直接返回类型化的输出
            return NovelLoadOutput(
                chapter_list=chapters,
                volume_list=volumes
            )
    ```
    """
    
    # 元数据（子类必须定义）
    node_type: ClassVar[str]
    category: ClassVar[str]
    label: ClassVar[str]
    description: ClassVar[str] = ""
    
    # 输入/输出模型（子类必须定义）
    input_model: ClassVar[Type[TInput]]
    output_model: ClassVar[Type[TOutput]]
    
    def __init__(self, context: ExecutionContext):
        """初始化节点
        
        Args:
            context: 执行上下文（包含 session, variables 等）
        """
        self.context = context
        self._cleanup_tasks: List[Any] = []  # 需要清理的任务列表
    
    async def cleanup(self):
        """清理节点资源
        
        当工作流暂停或取消时调用，用于清理节点内部的资源：
        - 取消正在运行的子任务
        - 关闭文件句柄
        - 释放数据库连接
        - 清理临时文件
        
        子类可以重写此方法来实现自定义清理逻辑。
        
        默认实现：取消所有通过 register_task() 注册的任务。
        """
        if self._cleanup_tasks:
            from loguru import logger
            logger.info(f"[{self.node_type}] 清理 {len(self._cleanup_tasks)} 个任务")
            
            for task in self._cleanup_tasks:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass  # 正常取消
                    except Exception as e:
                        logger.error(f"[{self.node_type}] 取消任务时出错: {e}")
            
            self._cleanup_tasks.clear()
    
    def register_task(self, task):
        """注册需要清理的任务
        
        节点内部创建的异步任务应该通过此方法注册，
        以便在工作流暂停时能够正确取消。
        
        Args:
            task: asyncio.Task 对象
        """
        self._cleanup_tasks.append(task)
    
    @classmethod
    def get_metadata(cls) -> NodeMetadata:
        """获取节点元数据
        
        自动从 Pydantic 模型生成完整的 JSON Schema。
        
        Returns:
            NodeMetadata 对象
        """
        # 输入 Schema（自动从 Pydantic 生成）
        input_schema = {}
        if hasattr(cls, 'input_model') and cls.input_model:
            input_schema = cls.input_model.model_json_schema()
        
        # 输出 Schema（自动从 Pydantic 生成）
        output_schema = {}
        if hasattr(cls, 'output_model') and cls.output_model:
            output_schema = cls.output_model.model_json_schema()
        
        return NodeMetadata(
            type=cls.node_type,
            category=cls.category,
            label=cls.label,
            description=cls.description,
            documentation=inspect.getdoc(cls) or "",
            input_schema=input_schema,
            output_schema=output_schema,
            executor=cls
        )
    
    @abstractmethod
    async def execute(self, inputs: TInput) -> AsyncIterator[Union['ProgressEvent', TOutput]]:
        """执行节点逻辑（统一流式接口）
        
        节点可以 yield 两种类型：
        1. ProgressEvent：报告进度（可选，用于批量处理）
        2. TOutput：最终结果（必须，至少 yield 一次）
        
        Args:
            inputs: 类型化的输入模型
            
        Yields:
            ProgressEvent: 进度事件（可选，用于批量处理）
            TOutput: 输出模型实例（必须，至少 yield 一次）
            
        注意：
        - 简单节点：只 yield 结果，零额外代码
        - 批量处理节点：可以多次 yield ProgressEvent 报告进度，最后 yield 结果
        - 最后一次 yield 的 TOutput 会被作为节点的输出
        
        示例：
            # 简单节点（只 yield 结果）
            async def execute(self, inputs):
                result = await process(inputs)
                yield Output(result=result)
            
            # 批量处理节点（yield 进度 + 结果）
            async def execute(self, inputs):
                for i, item in enumerate(inputs.items):
                    result = await process(item)
                    
                    # 报告进度（自动保存检查点）
                    yield ProgressEvent(
                        percent=(i + 1) / len(inputs.items) * 100,
                        message=f"已处理 {i + 1}/{len(inputs.items)}"
                    )
                
                # 返回最终结果
                yield Output(results=results)
        
        Raises:
            Exception: 执行失败时抛出异常
        """
        raise NotImplementedError


# --- 便利的基类 ---

class NoInputNode(BaseNode[BaseModel, TOutput]):
    """无输入节点的便利基类
    
    用于不需要输入参数的节点（如触发器）。
    """
    
    class EmptyInput(BaseModel):
        """空输入"""
        pass
    
    input_model = EmptyInput
    
    async def execute(self, inputs: BaseModel) -> AsyncIterator[Union['ProgressEvent', TOutput]]:
        """执行节点（忽略输入）"""
        result = await self.execute_no_input()
        yield result
    
    @abstractmethod
    async def execute_no_input(self) -> TOutput:
        """无输入的执行方法"""
        raise NotImplementedError


class NoOutputNode(BaseNode[TInput, BaseModel]):
    """无输出节点的便利基类
    
    用于只有副作用、不返回数据的节点（如日志、显示）。
    """
    
    class EmptyOutput(BaseModel):
        """空输出"""
        pass
    
    output_model = EmptyOutput
    
    async def execute(self, inputs: TInput) -> AsyncIterator[Union['ProgressEvent', BaseModel]]:
        """执行节点（无返回值）"""
        await self.execute_no_output(inputs)
        yield self.EmptyOutput()
    
    @abstractmethod
    async def execute_no_output(self, inputs: TInput) -> None:
        """无输出的执行方法"""
        raise NotImplementedError


# --- 工具函数 ---
