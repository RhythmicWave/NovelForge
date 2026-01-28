"""运行管理器 - 统一管理工作流运行"""

from typing import Optional, Dict, Any
from datetime import datetime
from sqlmodel import Session, select
from loguru import logger

from app.db.models import Workflow, WorkflowRun
from .graph_builder import GraphBuilder
from .executor import WorkflowExecutor
from .state_manager import StateManager
from .scheduler import WorkflowScheduler
from ..types import WorkflowSettings


class RunManager:
    """工作流运行管理器
    
    职责：
    - 创建和启动运行
    - 管理运行生命周期
    - 提供暂停/恢复/取消接口
    - 协调各个组件
    """
    
    def __init__(self, session: Session):
        self.session = session
        self.graph_builder = GraphBuilder()
        self.state_manager = StateManager(session)
        self.scheduler = WorkflowScheduler(max_concurrent_runs=5)
    
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
            trigger_data: 触发数据（如卡片信息）
            params: 运行参数
            idempotency_key: 幂等键
            
        Returns:
            WorkflowRun: 运行记录
        """
        # 检查幂等性
        if idempotency_key:
            stmt = select(WorkflowRun).where(
                WorkflowRun.idempotency_key == idempotency_key
            )
            existing = self.session.exec(stmt).first()
            if existing:
                logger.info(
                    f"[RunManager] 幂等键已存在，返回现有运行: "
                    f"run_id={existing.id}"
                )
                return existing
        
        # 获取工作流
        workflow = self.session.get(Workflow, workflow_id)
        if not workflow:
            raise ValueError(f"工作流不存在: {workflow_id}")
        
        if not workflow.is_active:
            raise ValueError(f"工作流未激活: {workflow_id}")
        
        # 创建运行记录
        run = WorkflowRun(
            workflow_id=workflow_id,
            definition_version=workflow.version,
            status="queued",
            scope_json=trigger_data,
            params_json=params,
            idempotency_key=idempotency_key
        )
        
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        
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
        run_id = run.id
        
        try:
            # 更新状态为运行中
            self.state_manager.update_run_status(run_id, "running")
            
            # 解析工作流定义
            definition = workflow.definition_json or {}
            
            # 构建执行图
            logger.info(f"[RunManager] 构建执行图: run_id={run_id}")
            graph = self.graph_builder.build(definition)
            
            # 解析执行设置
            settings_data = definition.get("settings", {})
            settings = WorkflowSettings(
                max_execution_time=run.max_execution_time,
                timeout=settings_data.get("timeout", 300),
                error_handling=settings_data.get("errorHandling", "stop"),
                max_concurrency=settings_data.get("maxConcurrency", 5),
                log_level=settings_data.get("logLevel", "info")
            )
            
            # 准备初始变量
            variables = {}
            
            # 从定义中加载全局变量
            for var_def in definition.get("variables", []):
                variables[var_def["name"]] = var_def.get("value")
            
            # 添加触发数据
            if run.scope_json:
                variables["trigger"] = run.scope_json
            
            # 添加参数
            if run.params_json:
                variables["params"] = run.params_json
            
            # 创建执行器
            executor = WorkflowExecutor(
                state_manager=self.state_manager
            )
            
            # 执行工作流（带超时控制）
            if settings.max_execution_time:
                import asyncio
                result = await asyncio.wait_for(
                    executor.execute(run_id, graph, settings, variables),
                    timeout=settings.max_execution_time
                )
            else:
                result = await executor.execute(
                    run_id, graph, settings, variables
                )
            
            # 更新状态为成功
            self.state_manager.update_run_status(
                run_id,
                "succeeded",
                summary_json={
                    "executed_nodes": result["executed_nodes"],
                    "outputs": result["outputs"]
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
                    "progress": ns.progress,
                    "error": ns.error_message,
                    "inputs_json": ns.inputs_json,
                    "outputs_json": ns.outputs_json,
                    "logs_json": ns.logs_json
                }
                for ns in node_states
            ]
        }
    

