"""统一的错误处理器

职责：
- 统一处理节点执行错误
- 处理任务取消
- 保存错误信息到状态
"""

import asyncio
from typing import TYPE_CHECKING
from loguru import logger
from sqlmodel import Session

if TYPE_CHECKING:
    from .execution_state import ExecutionState
    from ..engine.execution_plan import Statement
    from .async_executor import ProgressEvent


class ExecutionError(Exception):
    """执行错误基类"""
    def __init__(self, node_id: str, message: str, details: dict = None):
        self.node_id = node_id
        self.message = message
        self.details = details or {}
        super().__init__(message)


class NodeExecutionError(ExecutionError):
    """节点执行错误"""
    pass


class CheckpointError(ExecutionError):
    """检查点错误"""
    pass


class ErrorHandler:
    """统一的错误处理器"""
    
    @staticmethod
    async def handle_node_error(
        error: Exception,
        stmt: 'Statement',
        execution_state: 'ExecutionState',
        session: Session
    ) -> 'ProgressEvent':
        """处理节点执行错误
        
        Args:
            error: 异常对象
            stmt: 语句对象
            execution_state: 执行状态
            session: 数据库会话
            
        Returns:
            错误事件
        """
        from .async_executor import ProgressEvent
        
        logger.error(f"[ErrorHandler] 节点执行失败: {stmt.variable}, 错误: {error}")
        
        # 更新节点状态
        execution_state.update_node_state(
            node_id=stmt.variable,
            node_type=stmt.node_type or "unknown",
            status="error",
            error=str(error)
        )
        
        # 保存状态
        execution_state.save(session)
        
        # 返回错误事件
        return ProgressEvent(
            statement=stmt,
            type='error',
            error=str(error)
        )
    
    @staticmethod
    async def handle_cancellation(
        stmt: 'Statement',
        execution_state: 'ExecutionState',
        session: Session
    ):
        """处理任务取消
        
        当异步任务被取消时调用，保存当前进度。
        
        Args:
            stmt: 语句对象
            execution_state: 执行状态
            session: 数据库会话
        """
        logger.info(f"[ErrorHandler] 任务被取消: {stmt.variable}")
        
        # 获取当前进度
        node_state = execution_state.get_node_state(stmt.variable)
        current_progress = node_state.progress if node_state else 0.0
        
        # 标记为暂停状态
        execution_state.update_node_state(
            node_id=stmt.variable,
            node_type=stmt.node_type or "unknown",
            status="paused",
            progress=current_progress
        )
        
        # 保存状态
        execution_state.save(session)
        
        logger.info(f"[ErrorHandler] 任务取消已处理: {stmt.variable}, 进度={current_progress}%")
