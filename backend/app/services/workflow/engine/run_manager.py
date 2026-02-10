"""运行管理器 - 统一管理代码式工作流运行"""

from typing import Optional, Dict, Any
from sqlmodel import Session, select
from loguru import logger

from app.db.models import Workflow, WorkflowRun
from .state_manager import StateManager
from .scheduler import WorkflowScheduler


class RunManager:
    """工作流运行管理器
    
    职责：
    - 创建和启动运行
    - 管理运行生命周期
    - 提供暂停/恢复/取消接口
    - 协调各个组件
    
    只支持代码式工作流系统。
    """
    
    def __init__(self, session: Session):
        self.session = session
        self.state_manager = StateManager(session)
        self.scheduler = WorkflowScheduler(max_concurrent_runs=5)
        self.executors: Dict[int, AsyncExecutor] = {}  # 保存执行器引用（用于暂停/恢复）
    
    def create_run(
        self,
        workflow_id: int,
        trigger_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None
    ) -> WorkflowRun:
        """创建工作流运行
        
        Args:
            workflow_id: 工作流ID
            trigger_data: 触发数据（如卡片信息），会注入到 scope_json
            params: 运行参数，会注入到 params_json
            idempotency_key: 幂等键，防止重复执行
            
        Returns:
            WorkflowRun: 运行记录
        """
        # 检查幂等性（只检查正在运行的任务，避免阻止失败任务重试）
        if idempotency_key:
            stmt = select(WorkflowRun).where(
                WorkflowRun.idempotency_key == idempotency_key,
                WorkflowRun.status.in_(["queued", "running"])
            )
            existing = self.session.exec(stmt).first()
            if existing:
                logger.warning(
                    f"[RunManager] 幂等键冲突，任务正在运行: "
                    f"run_id={existing.id}, status={existing.status}"
                )
                return existing
        
        # 获取工作流
        workflow = self.session.get(Workflow, workflow_id)
        if not workflow:
            raise ValueError(f"工作流不存在: {workflow_id}")
        
        if not workflow.is_active:
            raise ValueError(f"工作流未激活: {workflow_id}")
        
        # 创建运行记录
        from datetime import datetime
        run = WorkflowRun(
            workflow_id=workflow_id,
            definition_version=workflow.dsl_version,  # 使用 dsl_version 代替 version
            status="queued",
            scope_json=trigger_data,
            params_json=params,
            idempotency_key=idempotency_key,
            created_at=datetime.now()  # 使用本地时间而不是 UTC
        )
        
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        
        # 清理该 run_id 的旧节点状态（确保干净的开始）
        self.state_manager.clear_node_states(run.id)
        
        logger.info(
            f"[RunManager] 创建运行: run_id={run.id}, "
            f"workflow_id={workflow_id}"
        )
        
        return run
    
    async def start_run(
        self,
        run_id: int,
        priority: int = 0
    ) -> None:
        """启动工作流运行
        
        Args:
            run_id: 运行ID
            priority: 优先级
        """
        run = self.session.get(WorkflowRun, run_id)
        if not run:
            raise ValueError(f"运行不存在: {run_id}")
        
        workflow = self.session.get(Workflow, run.workflow_id)
        if not workflow:
            raise ValueError(f"工作流不存在: {run.workflow_id}")
        
        # 创建执行协程
        executor_coro = self._execute_run(run, workflow)
        
        # 调度执行
        await self.scheduler.schedule_run(run_id, executor_coro, priority)
    
    async def _execute_run(
        self,
        run: WorkflowRun,
        workflow: Workflow
    ) -> None:
        """执行运行（内部方法）"""
        from ..parser.marker_parser import WorkflowParser
        from .async_executor import AsyncExecutor
        
        run_id = run.id

        try:
            # 更新状态为运行中
            self.state_manager.update_run_status(run_id, "running")

            # 解析工作流定义
            definition = workflow.definition_json or {}
            code = definition.get("code", "")

            if not code:
                raise ValueError("工作流缺少代码内容")

            logger.info(f"[RunManager] 解析代码式工作流: run_id={run_id}")

            # 解析代码
            parser = WorkflowParser()
            plan = parser.parse(code)

            logger.info(f"[RunManager] 执行代码式工作流: run_id={run_id}, 语句数={len(plan.statements)}")

            # 准备初始上下文（注入触发器数据）
            initial_context = {}

            # 将 scope_json 和 params_json 直接展开到顶层
            if run.scope_json:
                initial_context.update(run.scope_json)
            if run.params_json:
                initial_context.update(run.params_json)

            # 执行工作流（流式）
            executor = AsyncExecutor(
                session=self.state_manager.session,
                state_manager=self.state_manager,
                run_id=run_id
            )
            
            # 保存执行器引用（用于暂停/恢复）
            self.executors[run_id] = executor
            
            try:
                # 消费所有事件（触发器场景不需要处理进度）
                async for event in executor.execute_stream(plan, initial_context):
                    pass  # 可以在这里添加日志记录
                
                # 获取最终结果
                result_context = executor.context
            finally:
                # 清理执行器引用
                if run_id in self.executors:
                    del self.executors[run_id]

            # 更新状态为成功
            self.state_manager.update_run_status(
                run_id,
                "succeeded",
                summary_json={
                    "variables": list(result_context.keys()),
                    "outputs": self.state_manager._make_json_serializable(result_context)
                }
            )

            logger.info(f"[RunManager] 运行成功: run_id={run_id}")

        except Exception as e:
            error_msg = str(e)
            logger.exception(f"[RunManager] 运行失败: run_id={run_id}")

            # 判断是否超时
            import asyncio
            if isinstance(e, asyncio.TimeoutError):
                self.state_manager.update_run_status(run_id, "timeout")
            else:
                self.state_manager.update_run_status(run_id, "failed")
                self.state_manager.save_error(run_id, error_msg)
    
    async def cancel_run(self, run_id: int) -> bool:
        """取消运行
        
        Args:
            run_id: 运行ID
            
        Returns:
            是否成功取消
        """
        # 尝试从调度器取消
        if self.scheduler.cancel_run(run_id):
            self.state_manager.update_run_status(run_id, "cancelled")
            logger.info(f"[RunManager] 运行已取消: run_id={run_id}")
            return True
        
        return False
    
    async def pause_run(self, run_id: int) -> bool:
        """暂停运行
        
        Args:
            run_id: 运行ID
            
        Returns:
            是否成功暂停
        """
        executor = self.executors.get(run_id)
        if executor:
            executor.pause()
            self.state_manager.update_run_status(run_id, "paused")
            logger.info(f"[RunManager] 运行已暂停: run_id={run_id}")
            return True
        
        logger.warning(f"[RunManager] 无法暂停运行（执行器不存在）: run_id={run_id}")
        return False
    
    async def resume_run(self, run_id: int) -> bool:
        """恢复运行
        
        Args:
            run_id: 运行ID
            
        Returns:
            是否成功恢复
        """
        run = self.session.get(WorkflowRun, run_id)
        if not run:
            logger.warning(f"[RunManager] 运行不存在: run_id={run_id}")
            return False
        
        if run.status != "paused":
            logger.warning(f"[RunManager] 运行状态不是暂停: run_id={run_id}, status={run.status}")
            return False
        
        # 检查执行器是否存在
        executor = self.executors.get(run_id)
        if executor:
            # 执行器存在，直接恢复
            executor.resume()
            self.state_manager.update_run_status(run_id, "running")
            logger.info(f"[RunManager] 运行已恢复: run_id={run_id}")
            return True
        else:
            # 执行器不存在（服务器重启），重新启动运行
            logger.info(f"[RunManager] 执行器不存在，重新启动运行: run_id={run_id}")
            workflow = self.session.get(Workflow, run.workflow_id)
            if not workflow:
                logger.error(f"[RunManager] 工作流不存在: workflow_id={run.workflow_id}")
                return False
            
            # 重新启动（会自动恢复状态）
            await self.start_run(run_id)
            return True
    
    def get_run_status(self, run_id: int) -> Optional[Dict[str, Any]]:
        """获取运行状态
        
        Args:
            run_id: 运行ID
            
        Returns:
            运行状态信息
        """
        run = self.session.get(WorkflowRun, run_id)
        if not run:
            return None
        
        # 获取节点状态
        node_states = self.state_manager.get_all_node_states(run_id)
        
        return {
            "run_id": run.id,
            "workflow_id": run.workflow_id,
            "status": run.status,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "error": run.error_json,
            "nodes": [
                {
                    "node_id": ns.node_id,
                    "node_type": ns.node_type,
                    "status": ns.status,
                    "progress": int(ns.progress) if ns.progress is not None else 0,
                    "error": ns.error_message,
                    "outputs_json": ns.outputs_json
                }
                for ns in node_states
            ]
        }
