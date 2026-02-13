"""异步执行器

基于代码式工作流的异步执行器，支持SSE推送进度。
完全流式设计，所有节点通过 async for 消费事件。
"""

import asyncio
from typing import Dict, Any, List, Optional, AsyncIterator, TYPE_CHECKING
from dataclasses import dataclass
from datetime import datetime
from loguru import logger
from sqlmodel import Session

from .execution_plan import ExecutionPlan, Statement
from .execution_state import ExecutionState, CheckpointData
from .error_handler import ErrorHandler
from ..registry import get_registered_nodes
from ..expressions.evaluator import evaluate_expression

if TYPE_CHECKING:
    from .state_manager import StateManager


# 统一的进度事件（节点和执行器共用）
@dataclass
class ProgressEvent:
    """进度事件（统一类型）
    
    用于节点报告执行进度，执行器自动保存为检查点。
    
    节点使用时（简单版）：
        yield ProgressEvent(
            percent=50.0,
            message="已处理 30/60",
            data={'processed_count': 30}
        )
    
    执行器使用时（包含 statement）：
        yield ProgressEvent(
            statement=stmt,
            type='progress',
            percent=50.0,
            message="已处理 30/60"
        )
    
    Attributes:
        percent: 进度百分比（0-100）
        message: 进度消息
        data: 检查点数据（节点使用，可选，轻量级元数据）
            - 只保存位置信息：索引、计数器、ID 等
            - 不保存业务数据：卡片内容、处理结果等
            - 大小限制：< 10KB
        statement: 语句对象（执行器使用）
        type: 事件类型（执行器使用）
        result: 执行结果（执行器使用）
        error: 错误信息（执行器使用）
    """
    # 节点层字段
    percent: float = 0.0  # 0-100
    message: str = ""
    data: Optional[Dict[str, Any]] = None
    
    # 执行器层字段
    statement: Optional[Statement] = None
    type: Optional[str] = None  # 'start', 'progress', 'complete', 'error', 'workflow_complete'
    result: Optional[Any] = None
    error: Optional[str] = None


class AsyncExecutor:
    """异步执行器
    
    完全流式设计：
    1. 所有节点通过 async for 消费事件
    2. 异步任务收集并并行执行
    3. wait 节点等待并转发事件
    4. 同步节点自动等待所有异步任务
    5. 支持暂停/恢复和断点续传
    
    使用统一的 ExecutionState 管理所有状态。
    """

    def __init__(self, session: Session, state_manager: Optional['StateManager'] = None, run_id: int = 0):
        self.session = session  # 数据库会话
        self.state_manager = state_manager  # 状态管理器（可选，用于兼容）
        self.run_id = run_id  # 运行ID
        self.execution_state = ExecutionState(run_id)  # 统一的执行状态
        self.node_registry = get_registered_nodes()
        self.async_tasks: Dict[str, asyncio.Task] = {}  # 异步任务（保存引用用于取消）
        self.node_instances: Dict[str, Any] = {}  # 节点实例（用于清理）
        self.event_queue: asyncio.Queue = asyncio.Queue()  # 事件队列（实时转发）
        self.pending_async_tasks: int = 0  # 待完成的异步任务数量
        self.pause_event = asyncio.Event()  # 暂停信号
        self.pause_event.set()  # 默认不暂停
        self.is_paused = False  # 是否已暂停
    
    @property
    def context(self) -> Dict[str, Any]:
        """执行上下文（兼容旧代码）"""
        return self.execution_state.context
    
    @property
    def completed_statements(self) -> set:
        """已完成的语句（兼容旧代码）"""
        return self.execution_state.completed_nodes

    async def execute_stream(
        self,
        plan: ExecutionPlan,
        initial_context: Optional[Dict[str, Any]] = None
    ) -> AsyncIterator[ProgressEvent]:
        """流式执行工作流，返回进度事件
        
        使用事件队列实时转发进度：
        1. 异步任务的进度事件实时放入队列
        2. 主协程从队列中读取事件并 yield
        3. 支持多个异步任务同时报告进度
        4. 支持暂停/恢复和断点续传
        
        Args:
            plan: 执行计划
            initial_context: 初始上下文
            
        Yields:
            进度事件
        """
        # 尝试恢复状态（断点续传）
        is_resuming = False
        if self.run_id:
            # 从数据库加载完整状态
            self.execution_state = ExecutionState.load(self.run_id, self.session)
            
            # 只有当有已完成的节点时才算恢复执行
            if self.execution_state.completed_nodes:
                is_resuming = True
                logger.info(
                    f"[AsyncExecutor] 检测到恢复执行: run_id={self.run_id}, "
                    f"已完成={len(self.execution_state.completed_nodes)}个节点"
                )
            else:
                # 有 run_id 但没有已完成的节点，说明是新执行或失败重试
                self.execution_state.context = initial_context or {}
                logger.info(f"[AsyncExecutor] 新执行或重试: run_id={self.run_id}, 使用初始上下文")
        else:
            # 新执行，使用初始上下文
            self.execution_state.context = initial_context or {}
            logger.info(f"[AsyncExecutor] 新执行: 使用初始上下文")
        
        # 如果是恢复执行，先推送已完成节点的状态（让前端显示）
        if is_resuming:
            for node_id in self.execution_state.completed_nodes:
                node_state = self.execution_state.get_node_state(node_id)
                if node_state and node_state.status == "success":
                    # 找到对应的语句
                    stmt = next((s for s in plan.statements if s.variable == node_id), None)
                    if stmt:
                        # 推送已完成事件
                        await self.event_queue.put(ProgressEvent(
                            statement=stmt,
                            type='complete',
                            result=node_state.outputs,
                            message=f"[已恢复] {node_id}"
                        ))
                        logger.info(f"[AsyncExecutor] 推送已完成节点状态: {node_id}")
        
        logger.info(f"[AsyncExecutor] 开始流式执行工作流，共 {len(plan.statements)} 个语句")
        
        # 启动事件消费协程
        consumer_task = asyncio.create_task(self._process_statements(plan))
        
        try:
            # 从队列中读取事件并转发
            while True:
                event = await self.event_queue.get()
                
                if event is None:  # 结束标记
                    break
                    
                yield event
                
        finally:
            # 等待语句处理完成
            try:
                await consumer_task
            except Exception as e:
                logger.error(f"[AsyncExecutor] 语句处理失败: {e}")
                raise
    
    async def _process_statements(self, plan: ExecutionPlan):
        """处理所有语句（在单独的协程中运行）"""
        try:
            for stmt in plan.statements:
                # 跳过已完成的语句（断点续传）
                if self.execution_state.is_completed(stmt.variable):
                    logger.info(f"[AsyncExecutor] 跳过已完成的语句: {stmt.variable}")
                    continue
                
                # 检查暂停信号（如果已暂停，停止执行）
                if self.is_paused:
                    logger.info(f"[AsyncExecutor] 检测到暂停状态，停止执行")
                    break
                
                # 等待暂停信号（如果暂停，会在这里阻塞）
                await self.pause_event.wait()
                
                logger.info(f"[AsyncExecutor] 执行语句: {stmt.variable} (类型: {stmt.node_type}, async: {stmt.is_async}, disabled: {stmt.disabled})")
                
                # 跳过禁用的节点
                if stmt.disabled:
                    logger.info(f"[AsyncExecutor] 跳过禁用的节点: {stmt.variable}")
                    
                    # 发送跳过事件到队列
                    await self.event_queue.put(ProgressEvent(
                        statement=stmt,
                        type='skipped',
                        message=f"节点已禁用，跳过执行: {stmt.variable}"
                    ))
                    
                    # 将结果设置为 None（避免后续节点引用时出错）
                    self.execution_state.context[stmt.variable] = None
                    self.execution_state.completed_nodes.add(stmt.variable)
                    continue
                
                # 发送开始事件到队列
                await self.event_queue.put(ProgressEvent(
                    statement=stmt,
                    type='start',
                    message=f"开始执行: {stmt.variable}"
                ))
                
                try:
                    if stmt.is_async:
                        # 异步节点：创建任务，事件实时放入队列
                        logger.info(f"[AsyncNode] 创建异步任务: {stmt.variable}")
                        self.pending_async_tasks += 1
                        
                        # 创建任务，将事件实时放入队列（保存引用用于取消）
                        task = asyncio.create_task(
                            self._execute_async_node_to_queue(stmt),
                            name=f"async_node_{stmt.variable}"  # 设置任务名称便于调试
                        )
                        self.async_tasks[stmt.variable] = task
                        logger.info(f"[AsyncNode] 任务已创建并保存引用: {stmt.variable}")
                        # 不等待，继续下一个语句
                        
                    elif stmt.node_type == "Logic.Wait" or stmt.node_type == "_wait":
                        # wait 节点：等待指定的异步任务
                        # 支持两种配置格式：tasks (新) 和 wait_for (旧)
                        wait_for = stmt.config.get("tasks") or stmt.config.get("wait_for", [])
                        
                        # 确保 wait_for 是列表
                        if isinstance(wait_for, str):
                            # 如果是字符串，按逗号分割
                            wait_for = [v.strip() for v in wait_for.split(",") if v.strip()]
                        elif not isinstance(wait_for, list):
                            wait_for = [wait_for] if wait_for else []
                        
                        # 清理变量名：移除 $ 前缀（如果有）
                        wait_for = [v.lstrip('$') if isinstance(v, str) else v for v in wait_for]
                        
                        logger.info(f"[Wait] 等待异步任务: {','.join(wait_for)}")
                        
                        for var in wait_for:
                            if var in self.async_tasks:
                                # 异步任务还在运行，等待它完成
                                logger.info(f"[Wait] 等待异步任务完成: {var}")
                                await self.async_tasks[var]
                                del self.async_tasks[var]
                            elif var in self.execution_state.context:
                                # 变量已经在上下文中（已完成或恢复的节点）
                                logger.info(f"[Wait] 变量已存在于上下文: {var}")
                            else:
                                # 变量不存在
                                raise ValueError(f"等待的变量不存在: {var}")
                        
                        # 保存 wait 结果到上下文
                        self.execution_state.context[stmt.variable] = {
                            'waited_tasks': wait_for,
                            'count': len(wait_for)
                        }
                        
                        # wait 节点本身发送完成事件
                        await self.event_queue.put(ProgressEvent(
                            statement=stmt,
                            type='complete',
                            result=self.execution_state.context[stmt.variable]
                        ))
                        
                        # 标记为已完成
                        self.execution_state.completed_nodes.add(stmt.variable)
                        
                    elif stmt.node_type is None:
                        # 纯表达式
                        result = self._execute_expression(stmt)
                        self.execution_state.context[stmt.variable] = result
                        
                        # 保存节点输出
                        self.execution_state.update_node_state(
                            node_id=stmt.variable,
                            node_type="expression",
                            status="success",
                            progress=100.0,
                            outputs=result
                        )
                        self.execution_state.save(self.session)
                        
                        await self.event_queue.put(ProgressEvent(
                            statement=stmt,
                            type='complete',
                            result=result
                        ))
                        
                    else:
                        # 同步节点：直接执行，不等待异步任务
                        async for event in self._execute_node_stream(stmt):
                            await self.event_queue.put(event)
                    
                    # 标记语句已完成
                    self.execution_state.completed_nodes.add(stmt.variable)
                            
                except Exception as e:
                    logger.error(f"[AsyncExecutor] 语句执行失败: {stmt.variable}, 错误: {e}")
                    # 使用错误处理器
                    error_event = await ErrorHandler.handle_node_error(
                        e, stmt, self.execution_state, self.session
                    )
                    await self.event_queue.put(error_event)
                    raise
            
            # 工作流结束，等待所有剩余的异步任务
            if self.async_tasks:
                logger.info(f"[AsyncExecutor] 工作流结束，等待剩余 {len(self.async_tasks)} 个异步任务")
                for var, task in list(self.async_tasks.items()):
                    logger.info(f"[AsyncExecutor] 等待异步任务: {var}")
                    await task
                    del self.async_tasks[var]
            
            logger.info(f"[AsyncExecutor] 工作流流式执行完成，共定义 {len(self.execution_state.context)} 个变量")
            
            # 发送工作流完成事件
            await self.event_queue.put(ProgressEvent(
                statement=plan.statements[-1] if plan.statements else Statement(line_number=0, variable="", node_type=None, config={}, depends_on=[]),
                type='workflow_complete',
                message="工作流执行完成"
            ))
            
        finally:
            # 发送结束标记
            await self.event_queue.put(None)
    
    async def _execute_async_node_to_queue(self, stmt: Statement):
        """执行异步节点，并将事件实时放入队列"""
        try:
            async for event in self._execute_node_stream(stmt):
                await self.event_queue.put(event)
        except asyncio.CancelledError:
            # 任务被取消，使用错误处理器保存状态
            await ErrorHandler.handle_cancellation(
                stmt, self.execution_state, self.session
            )
            raise  # 重新抛出，让上层处理
        except Exception as e:
            # 节点执行错误
            logger.error(f"[AsyncNode] 异步节点执行失败: {stmt.variable}, 错误: {e}")
            error_event = await ErrorHandler.handle_node_error(
                e, stmt, self.execution_state, self.session
            )
            await self.event_queue.put(error_event)
            raise
        finally:
            self.pending_async_tasks -= 1

    async def _execute_node_stream(self, stmt: Statement) -> AsyncIterator[ProgressEvent]:
        """执行节点并流式返回事件（支持自动检查点）
        
        核心功能：
        1. 加载检查点（如果存在）并注入到 ExecutionContext
        2. 拦截所有 yield，自动保存检查点
        3. 转发进度事件到前端
        
        Args:
            stmt: 语句对象
            
        Yields:
            进度事件（progress 和 complete）
        """
        node_type = stmt.node_type
        
        # 获取节点执行器
        executor_fn = self.node_registry.get(node_type)
        if not executor_fn:
            raise ValueError(f"未注册的节点类型: {node_type}")
        
        # 解析配置，处理变量引用
        config = self._resolve_config(stmt.config)
        
        # 构建输入
        inputs = self._resolve_inputs(config)
        
        # === 初始化节点状态 ===
        self.execution_state.update_node_state(
            node_id=stmt.variable,
            node_type=node_type,
            status="running",
            progress=0.0
        )
        
        # === 1. 加载检查点 ===
        checkpoint_data = self.execution_state.get_checkpoint(stmt.variable)
        checkpoint = checkpoint_data.data if checkpoint_data else None
        
        if checkpoint:
            logger.info(
                f"[Checkpoint] 恢复节点 {stmt.variable}: "
                f"进度={checkpoint_data.percent}%, "
                f"数据={checkpoint}"
            )
        
        # 执行节点
        import inspect
        if inspect.isclass(executor_fn):
            # 类式节点 - 需要创建 ExecutionContext
            from ..types import ExecutionContext, WorkflowSettings
            
            # === 2. 创建执行上下文（注入检查点）===
            context = ExecutionContext(
                run_id=self.run_id or 0,
                node_id=stmt.variable,
                node_type=node_type,
                config=config,
                inputs=inputs,
                variables=self.execution_state.context,
                node_outputs={},
                settings=WorkflowSettings(),
                session=self.session,
                checkpoint=checkpoint  # 注入检查点数据
            )
            
            # 实例化节点
            node = executor_fn(context)
            
            # ⚠️ 保存节点实例引用（用于清理）
            self.node_instances[stmt.variable] = node
            
            # 准备输入数据（合并 config 和 inputs）
            if hasattr(executor_fn, 'input_model') and executor_fn.input_model:
                input_data = {**config, **inputs}
                input_instance = executor_fn.input_model(**input_data)
            else:
                raise ValueError(f"节点 {node_type} 缺少 input_model 定义")
            
            # === 3. 执行节点并拦截 yield ===
            result = None
            async for event in node.execute(input_instance):
                # 处理进度事件（节点的 ProgressEvent）
                if isinstance(event, ProgressEvent):
                    # === 自动保存检查点 ===
                    checkpoint_data = CheckpointData(
                        percent=event.percent,
                        message=event.message,
                        data=event.data,
                        timestamp=datetime.utcnow()
                    )
                    
                    self.execution_state.update_node_state(
                        node_id=stmt.variable,
                        node_type=node_type,
                        status="running",
                        progress=event.percent,
                        checkpoint=checkpoint_data
                    )
                    self.execution_state.save(self.session)
                    
                    # 转发进度事件（包装成执行器事件）
                    yield ProgressEvent(
                        statement=stmt,
                        type='progress',
                        percent=event.percent,
                        message=event.message
                    )
                else:
                    # 这是最终结果（Pydantic 模型）
                    result = event
            
            # 检查执行结果
            if result is None:
                raise ValueError(f"节点 {node_type} 没有返回结果")
            
            # 转换为字典
            if hasattr(result, 'model_dump'):
                final_result = result.model_dump()
            elif hasattr(result, 'dict'):
                final_result = result.dict()
            else:
                final_result = result
            
            # 保存到上下文（统一使用完整的输出字典）
            self.execution_state.context[stmt.variable] = final_result
            
            # === 4. 保存完成状态（100% 进度）===
            self.execution_state.update_node_state(
                node_id=stmt.variable,
                node_type=node_type,
                status="success",
                progress=100.0,
                outputs=final_result,
                checkpoint=CheckpointData(
                    percent=100.0,
                    message="完成",
                    data={'completed': True},
                    timestamp=datetime.utcnow()
                )
            )
            self.execution_state.save(self.session)
            
            # 发送完成事件
            yield ProgressEvent(
                statement=stmt,
                type='complete',
                result=final_result
            )
                
        elif inspect.iscoroutinefunction(executor_fn):
            # 异步函数节点
            result = await executor_fn(**inputs)
            self.execution_state.context[stmt.variable] = result
            
            # 保存节点输出
            self.execution_state.update_node_state(
                node_id=stmt.variable,
                node_type=node_type or "async_function",
                status="success",
                progress=100.0,
                outputs=result
            )
            self.execution_state.save(self.session)
            
            yield ProgressEvent(
                statement=stmt,
                type='complete',
                result=result
            )
        else:
            # 同步函数节点
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, lambda: executor_fn(**inputs))
            self.execution_state.context[stmt.variable] = result
            
            # 保存节点输出
            self.execution_state.update_node_state(
                node_id=stmt.variable,
                node_type=node_type or "sync_function",
                status="success",
                progress=100.0,
                outputs=result
            )
            self.execution_state.save(self.session)
            
            yield ProgressEvent(
                statement=stmt,
                type='complete',
                result=result
            )

    def _execute_expression(self, stmt: Statement) -> Any:
        """执行纯表达式"""
        expression = stmt.config.get("expression", "")
        logger.info(f"[Expression] 执行表达式: {expression}")
        
        # 使用表达式求值器求值
        context = self._resolve_context(stmt.depends_on)
        return evaluate_expression(expression, context)

    def _resolve_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """解析配置，处理变量引用（支持嵌套结构）"""
        resolved = {}
        for key, value in config.items():
            resolved[key] = self._resolve_value(value)
        return resolved

    def _resolve_value(self, value: Any) -> Any:
        """递归解析值，处理变量引用"""
        if isinstance(value, str):
            if value.startswith("${") and value.endswith("}"):
                # 表达式引用，如 ${len(items)}
                expression = value[2:-1]
                return evaluate_expression(expression, self.execution_state.context)
            elif value.startswith("$"):
                # 变量引用，如 $novel.chapter_list
                ref = value[1:]  # 去掉 $ 前缀
                return self._resolve_variable_reference(ref)
            else:
                return value
        elif isinstance(value, list):
            return [self._resolve_value(item) for item in value]
        elif isinstance(value, dict):
            return {k: self._resolve_value(v) for k, v in value.items()}
        else:
            return value

    def _resolve_variable_reference(self, ref: str) -> Any:
        """解析变量引用
        
        支持：
        - 简单变量：novel
        - 属性访问：novel.title
        - 嵌套属性：novel.metadata.author
        """
        parts = ref.split(".")
        value = self.execution_state.context.get(parts[0])
        
        if value is None:
            raise ValueError(f"变量不存在: {parts[0]}")
        
        # 处理属性访问
        for part in parts[1:]:
            if isinstance(value, dict):
                value = value.get(part)
            else:
                value = getattr(value, part, None)
            
            if value is None:
                raise ValueError(f"属性不存在: {ref}")
        
        return value

    def _resolve_inputs(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """从配置中提取输入参数"""
        # 对于大多数节点，config 就是 inputs
        return config

    def _resolve_context(self, depends_on: List[str]) -> Dict[str, Any]:
        """解析依赖的上下文"""
        context = {}
        for var in depends_on:
            if var in self.execution_state.context:
                context[var] = self.execution_state.context[var]
        return context

    def pause(self):
        """暂停执行
        
        立即取消所有异步任务并暂停执行。
        不等待任务完成，让它们在后台取消。
        """
        self.is_paused = True
        self.pause_event.clear()
        
        # 清理所有节点实例（不等待完成）
        if self.node_instances:
            logger.info(f"[AsyncExecutor] 清理 {len(self.node_instances)} 个节点实例")
            for var, node in list(self.node_instances.items()):
                try:
                    logger.info(f"[AsyncExecutor] 清理节点: {var}")
                    # 创建清理任务但不等待（后台清理）
                    asyncio.create_task(node.cleanup())
                except Exception as e:
                    logger.error(f"[AsyncExecutor] 创建清理任务失败: {var}, 错误: {e}")
        
        # 取消所有异步任务（不等待完成）
        if self.async_tasks:
            logger.info(f"[AsyncExecutor] 取消 {len(self.async_tasks)} 个异步任务")
            for var, task in list(self.async_tasks.items()):
                if not task.done():
                    logger.info(f"[AsyncExecutor] 取消异步任务: {var}")
                    task.cancel()
                    # ⚠️ 不等待任务完成，让它在后台取消
        
        logger.info(f"[AsyncExecutor] 工作流已暂停: run_id={self.run_id}")
    
    def resume(self):
        """恢复执行
        
        恢复之前暂停的工作流执行。
        """
        self.is_paused = False
        self.pause_event.set()
        logger.info(f"[AsyncExecutor] 工作流已恢复: run_id={self.run_id}")
    
    def is_paused(self) -> bool:
        """检查是否处于暂停状态"""
        return not self.pause_event.is_set()
