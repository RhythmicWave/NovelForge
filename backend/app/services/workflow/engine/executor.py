"""工作流执行器 - 核心执行逻辑"""

import asyncio
from typing import Dict, Any, List, Set, Optional, Callable
from datetime import datetime
from loguru import logger

from ..types import (
    ExecutionGraph, ExecutionContext, ExecutionResult,
    WorkflowSettings, NodeStatus
)
from .state_manager import StateManager
from ..registry import get_registered_nodes


class WorkflowExecutor:
    """工作流执行器
    
    职责：
    - 执行工作流图
    - 管理节点并发执行
    - 处理节点依赖
    - 错误处理和重试
    - 超时控制
    """
    
    def __init__(
        self,
        state_manager: StateManager
    ):
        self.state_manager = state_manager
        self.node_registry = get_registered_nodes()
    
    async def execute(
        self,
        run_id: int,
        graph: ExecutionGraph,
        settings: WorkflowSettings,
        initial_variables: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """执行工作流
        
        Args:
            run_id: 运行ID
            graph: 执行图
            settings: 执行设置
            initial_variables: 初始变量
            
        Returns:
            执行结果（包含所有节点输出）
        """
        logger.info(f"[Executor] 开始执行工作流: run_id={run_id}")
        
        # 初始化执行状态
        variables = initial_variables or {}
        node_outputs: Dict[str, Dict[str, Any]] = {}
        executed: Set[str] = set()
        failed: Set[str] = set()
        
        # 不预先创建节点状态，只在执行时创建
        # 这样未执行的节点就不会有状态记录
        
        logger.info(f"[Executor] 图中不可达节点: {graph.unreachable_nodes}")
        logger.info(f"[Executor] 起始节点: {graph.start_nodes}")
        
        # 立即标记不可达节点为 skipped
        for node_id in graph.unreachable_nodes:
            node = graph.nodes.get(node_id)
            if node:
                self.state_manager.create_node_state(
                    run_id=run_id,
                    node_id=node_id,
                    node_type=node.get("type", "unknown")
                )
                self.state_manager.update_node_status(
                    run_id=run_id,
                    node_id=node_id,
                    status="skipped"
                )
                logger.info(f"[Executor] ✓ 孤立节点标记为 skipped: {node_id}")
        
        try:
            # 执行图
            await self._execute_graph(
                run_id=run_id,
                graph=graph,
                settings=settings,
                variables=variables,
                node_outputs=node_outputs,
                executed=executed,
                failed=failed
            )
            
            # 将未执行的节点标记为 skipped（排除已标记的不可达节点）
            all_nodes = set(graph.nodes.keys())
            skipped_nodes = all_nodes - executed - failed - graph.unreachable_nodes
            
            logger.info(f"[Executor] 所有节点: {all_nodes}")
            logger.info(f"[Executor] 已执行: {executed}")
            logger.info(f"[Executor] 失败: {failed}")
            logger.info(f"[Executor] 跳过: {skipped_nodes}")
            
            for node_id in skipped_nodes:
                # 先创建状态记录
                node = graph.nodes.get(node_id)
                if node:
                    self.state_manager.create_node_state(
                        run_id=run_id,
                        node_id=node_id,
                        node_type=node.get("type", "unknown")
                    )
                    self.state_manager.update_node_status(
                        run_id=run_id,
                        node_id=node_id,
                        status="skipped"
                    )
                    logger.info(f"[Executor] ✓ 节点标记为 skipped: {node_id}")
            
            # 保存最终状态（提取 ExecutionResult 的 outputs）
            outputs_dict = {
                node_id: result.outputs if hasattr(result, 'outputs') else result
                for node_id, result in node_outputs.items()
            }
            self.state_manager.save_run_state(run_id, {
                "variables": variables,
                "node_outputs": outputs_dict
            })
            
            logger.info(
                f"[Executor] 工作流执行完成: run_id={run_id}, "
                f"成功={len(executed)}, 失败={len(failed)}, 跳过={len(skipped_nodes)}"
            )
            
            return {
                "success": len(failed) == 0,
                "executed_nodes": list(executed),
                "failed_nodes": list(failed),
                "skipped_nodes": list(skipped_nodes),
                "outputs": outputs_dict,
                "variables": variables
            }
            
        except Exception as e:
            logger.exception(f"[Executor] 工作流执行失败: run_id={run_id}")
            raise
    
    async def _execute_graph(
        self,
        run_id: int,
        graph: ExecutionGraph,
        settings: WorkflowSettings,
        variables: Dict[str, Any],
        node_outputs: Dict[str, ExecutionResult],
        executed: Set[str],
        failed: Set[str]
    ) -> None:
        """执行图（支持并发）"""
        # 当前正在运行的任务
        running_tasks: Dict[str, asyncio.Task] = {}
        
        # 待执行队列（已就绪的节点）
        ready_queue: List[str] = list(graph.start_nodes)
        logger.info(f"[Executor] 初始就绪队列: {ready_queue}")
        
        while ready_queue or running_tasks:
            # 启动新任务（受并发限制）
            while (
                ready_queue and 
                len(running_tasks) < settings.max_concurrency
            ):
                node_id = ready_queue.pop(0)
                
                # 创建执行任务
                task = asyncio.create_task(
                    self._execute_node(
                        run_id=run_id,
                        node_id=node_id,
                        graph=graph,
                        settings=settings,
                        variables=variables,
                        node_outputs=node_outputs
                    )
                )
                running_tasks[node_id] = task
            
            if not running_tasks:
                break
            
            # 等待任意一个任务完成
            done, pending = await asyncio.wait(
                running_tasks.values(),
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # 处理完成的任务
            for task in done:
                # 找到对应的节点ID
                completed_node_id = None
                for nid, t in running_tasks.items():
                    if t == task:
                        completed_node_id = nid
                        break
                
                if not completed_node_id:
                    continue
                
                # 移除任务
                del running_tasks[completed_node_id]
                
                try:
                    # 获取执行结果
                    result = await task
                    
                    if result.success:
                        executed.add(completed_node_id)
                        # 存储完整的 ExecutionResult 以便访问 activated_ports
                        node_outputs[completed_node_id] = result
                        
                        # 检查后继节点是否就绪
                        for successor_id in graph.get_successors(completed_node_id):
                            if self._is_node_ready(
                                successor_id, graph, executed, failed, node_outputs
                            ):
                                if successor_id not in ready_queue:
                                    ready_queue.append(successor_id)
                    else:
                        failed.add(completed_node_id)
                        
                        # 根据错误处理策略决定是否继续
                        if settings.error_handling == "stop":
                            # 取消所有运行中的任务
                            for t in running_tasks.values():
                                t.cancel()
                            raise Exception(
                                f"节点执行失败: {completed_node_id}, "
                                f"错误: {result.error}"
                            )
                        # 如果是 continue，则继续执行其他节点
                
                except Exception as e:
                    logger.exception(
                        f"[Executor] 节点任务异常: {completed_node_id}"
                    )
                    failed.add(completed_node_id)
                    
                    if settings.error_handling == "stop":
                        # 取消所有运行中的任务
                        for t in running_tasks.values():
                            t.cancel()
                        raise
    
    def _extract_node_inputs(
        self,
        node_id: str,
        graph: ExecutionGraph,
        node_outputs: Dict[str, ExecutionResult]
    ) -> Dict[str, Any]:
        """从边中提取节点的输入数据
        
        遍历所有连接到该节点的边，从源节点的输出中提取数据。
        如果多个边连接到同一个目标端口,只使用成功节点的数据。
        """
        inputs = {}
        
        # 查找所有连接到该节点的边
        for edge in graph.edges:
            if edge.get("target") != node_id:
                continue
            
            source_id = edge.get("source")
            source_port = edge.get("sourceHandle") or "output"
            target_port = edge.get("targetHandle") or "input"
            
            # 获取源节点的输出
            if source_id in node_outputs:
                source_result = node_outputs[source_id]
                
                # 只从成功的节点提取数据
                if not source_result.success:
                    continue
                    
                source_output = source_result.outputs
                
                # 从源节点的指定端口获取数据
                if source_port in source_output:
                    data = source_output[source_port]
                    # 如果该目标端口已有数据,不覆盖(保留第一个成功的连接)
                    if target_port not in inputs:
                        inputs[target_port] = data
        
        return inputs
    
    def _is_node_ready(
        self,
        node_id: str,
        graph: ExecutionGraph,
        executed: Set[str],
        failed: Set[str],
        node_outputs: Dict[str, ExecutionResult]
    ) -> bool:
        """检查节点是否就绪（所有依赖都已完成且有激活的输入端口）"""
        dependencies = graph.get_dependencies(node_id)
        
        # 检查所有依赖节点是否已执行
        for dep_id in dependencies:
            if dep_id not in executed:
                # logger.debug(f"[Ready Check] 节点 {node_id} 依赖 {dep_id} 未执行")
                return False
        
        # 查找连接到该节点的边
        incoming_edges = [e for e in graph.edges if e.get("target") == node_id]
        
        # 如果没有任何输入边，则就绪（起始节点）
        if not incoming_edges:
            return True
        
        # 检查是否有激活的输入端口
        has_activated_input = False
        for edge in incoming_edges:
            source_id = edge.get("source")
            source_port = edge.get("sourceHandle") or "output"  # 默认输出端口
            
            if source_id not in node_outputs:
                continue
            
            # 获取源节点的执行结果
            source_result = node_outputs[source_id]
            
            # 获取激活的端口列表
            activated_ports = source_result.get_activated_ports()
            
            # 检查该端口是否被激活
            if source_port in activated_ports:
                has_activated_input = True
                break
        
        return has_activated_input
    
    async def _execute_node(
        self,
        run_id: int,
        node_id: str,
        graph: ExecutionGraph,
        settings: WorkflowSettings,
        variables: Dict[str, Any],
        node_outputs: Dict[str, ExecutionResult]
    ) -> ExecutionResult:
        """执行单个节点"""
        node = graph.get_node(node_id)
        if not node:
            return ExecutionResult(
                success=False,
                error=f"节点不存在: {node_id}"
            )
        
        node_type = node.get("type", "unknown")
        config = node.get("config", {})
        
        logger.info(f"[Executor] 执行节点: {node_id} ({node_type})")
        
        # 创建节点状态记录并设置为运行中
        self.state_manager.create_node_state(
            run_id=run_id,
            node_id=node_id,
            node_type=node_type
        )
        self.state_manager.update_node_status(
            run_id=run_id,
            node_id=node_id,
            status="running"
        )
        
        
        try:
            # 获取节点执行器
            executor_fn = self.node_registry.get(node_type)
            if not executor_fn:
                raise ValueError(f"未注册的节点类型: {node_type}")
            
            # 从边中提取输入数据
            inputs = self._extract_node_inputs(node_id, graph, node_outputs)
            
            # 构建执行上下文
            context = ExecutionContext(
                run_id=run_id,
                node_id=node_id,
                node_type=node_type,
                config=config,
                inputs=inputs,
                variables=variables,
                node_outputs=node_outputs,
                settings=settings,
                session=self.state_manager.session
            )
            
            # 保存输入
            self.state_manager.save_node_inputs(
                run_id=run_id,
                node_id=node_id,
                inputs=context.inputs
            )
            
            # 执行节点（带超时控制）
            timeout = config.get("timeout", settings.timeout)
            result = await asyncio.wait_for(
                self._call_executor(executor_fn, context),
                timeout=timeout
            )
            
            # 保存输出
            self.state_manager.save_node_outputs(
                run_id=run_id,
                node_id=node_id,
                outputs=result.outputs
            )
            
            # 保存日志
            for log in result.logs:
                self.state_manager.add_node_log(
                    run_id=run_id,
                    node_id=node_id,
                    **log
                )
            
            # 更新状态
            if result.success:
                self.state_manager.update_node_status(
                    run_id=run_id,
                    node_id=node_id,
                    status="success",
                    progress=100
                )
            else:
                self.state_manager.update_node_status(
                    run_id=run_id,
                    node_id=node_id,
                    status="error",
                    error_message=result.error
                )
            
            return result
            
        except asyncio.TimeoutError:
            error_msg = f"节点执行超时（>{timeout}秒）"
            logger.warning(f"[Executor] {error_msg}: {node_id}")
            
            self.state_manager.update_node_status(
                run_id=run_id,
                node_id=node_id,
                status="error",
                error_message=error_msg
            )
            
            return ExecutionResult(success=False, error=error_msg)
            
        except Exception as e:
            error_msg = str(e)
            logger.exception(f"[Executor] 节点执行异常: {node_id}")
            
            self.state_manager.update_node_status(
                run_id=run_id,
                node_id=node_id,
                status="error",
                error_message=error_msg
            )
            
            return ExecutionResult(success=False, error=error_msg)
    
    async def _call_executor(
        self,
        executor_fn: Any,
        context: ExecutionContext
    ) -> ExecutionResult:
        """调用节点执行器（处理同步/异步/类式）"""
        import inspect
        
        # 1. Class-Based Exec (v2.0)
        if inspect.isclass(executor_fn):
            return await self._execute_class_node(executor_fn, context)

        # 2. Function-Based (Legacy)
        if inspect.iscoroutinefunction(executor_fn):
            # 异步执行器
            return await executor_fn(context)
        else:
            # 同步执行器，在线程池中执行
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, executor_fn, context)

    async def _execute_class_node(
        self,
        node_cls: Any,
        context: ExecutionContext
    ) -> ExecutionResult:
        """执行类式节点"""
        # 实例化
        node = node_cls(context)
        
        # Setup
        if hasattr(node, 'setup'):
            await node.setup()
            
        try:
            # Config Validation
            config_model = getattr(node, 'config_model', None)
            config_instance = context.config
            
            if config_model:
                try:
                    # 使用 Pydantic 进行校验和转换
                    # 注意：context.config 是字典
                    config_instance = config_model(**context.config)
                except Exception as e:
                    return ExecutionResult(
                        success=False,
                        error=f"配置校验失败: {str(e)}"
                    )
            
            # Execute
            # 新版接口：execute(inputs, config)
            return await node.execute(context.inputs, config_instance)
            
        except Exception as e:
            logger.exception(f"[Executor] Class Node Execution Error: {context.node_id}")
            return ExecutionResult(
                success=False,
                error=str(e)
            )
        finally:
            # Teardown
            if hasattr(node, 'teardown'):
                await node.teardown()
