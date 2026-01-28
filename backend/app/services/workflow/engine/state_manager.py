"""状态管理器 - 管理工作流运行时状态"""

from typing import Dict, Any, Optional
from datetime import datetime
from sqlmodel import Session, select
from loguru import logger

from app.db.models import WorkflowRun, NodeExecutionState
from ..types import NodeStatus, RunStatus


class StateManager:
    """工作流状态管理器
    
    职责：
    - 持久化运行状态
    - 管理节点执行状态
    - 支持暂停/恢复
    - 提供状态查询接口
    """
    
    def __init__(self, session: Session):
        self.session = session
    
    # ==================== Run 状态管理 ====================
    
    def update_run_status(
        self, 
        run_id: int, 
        status: RunStatus,
        **kwargs
    ) -> WorkflowRun:
        """更新运行状态
        
        Args:
            run_id: 运行ID
            status: 新状态
            **kwargs: 其他要更新的字段
        """
        run = self.session.get(WorkflowRun, run_id)
        if not run:
            raise ValueError(f"运行不存在: {run_id}")
        
        run.status = status
        
        # 更新时间戳
        if status == "running" and not run.started_at:
            run.started_at = datetime.utcnow()
        elif status in ("succeeded", "failed", "cancelled", "timeout"):
            run.finished_at = datetime.utcnow()
        
        # 更新其他字段
        for key, value in kwargs.items():
            if hasattr(run, key):
                setattr(run, key, value)
        
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        
        # logger.debug(f"[StateManager] 运行状态更新: run_id={run_id}, status={status}")
        return run
    
    def save_run_state(
        self, 
        run_id: int, 
        state: Dict[str, Any]
    ) -> None:
        """保存运行时状态（变量、节点输出等）"""
        run = self.session.get(WorkflowRun, run_id)
        if not run:
            raise ValueError(f"运行不存在: {run_id}")
        
        # 转换状态使其可JSON序列化（例如将set转为list）
        serializable_state = self._make_json_serializable(state)
        
        run.state_json = serializable_state
        self.session.add(run)
        self.session.commit()
    
    def _make_json_serializable(self, obj: Any) -> Any:
        """递归转换对象为JSON可序列化的格式
        
        主要处理：
        - set -> list
        - 其他不可序列化类型根据需要添加
        """
        if isinstance(obj, set):
            return list(obj)
        elif isinstance(obj, dict):
            return {k: self._make_json_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._make_json_serializable(item) for item in obj]
        else:
            return obj
    
    def get_run_state(self, run_id: int) -> Optional[Dict[str, Any]]:
        """获取运行时状态"""
        run = self.session.get(WorkflowRun, run_id)
        if not run:
            return None
        return run.state_json or {}
    
    def save_error(
        self, 
        run_id: int, 
        error_message: str,
        error_details: Optional[Dict[str, Any]] = None
    ) -> None:
        """保存错误信息"""
        run = self.session.get(WorkflowRun, run_id)
        if not run:
            return
        
        run.error_json = {
            "message": error_message,
            "details": error_details or {},
            "timestamp": datetime.utcnow().isoformat()
        }
        self.session.add(run)
        self.session.commit()
    
    # ==================== Node 状态管理 ====================
    
    def create_node_state(
        self,
        run_id: int,
        node_id: str,
        node_type: str
    ) -> NodeExecutionState:
        """创建节点执行状态记录"""
        state = NodeExecutionState(
            run_id=run_id,
            node_id=node_id,
            node_type=node_type,
            status="idle"
        )
        self.session.add(state)
        self.session.commit()
        self.session.refresh(state)
        return state
    
    def update_node_status(
        self,
        run_id: int,
        node_id: str,
        status: NodeStatus,
        **kwargs
    ) -> Optional[NodeExecutionState]:
        """更新节点状态
        
        Args:
            run_id: 运行ID
            node_id: 节点ID
            status: 新状态
            **kwargs: 其他要更新的字段（如 progress, error_message 等）
        """
        # 查找节点状态记录
        stmt = select(NodeExecutionState).where(
            NodeExecutionState.run_id == run_id,
            NodeExecutionState.node_id == node_id
        )
        state = self.session.exec(stmt).first()
        
        if not state:
            logger.warning(
                f"[StateManager] 节点状态记录不存在: run_id={run_id}, node_id={node_id}"
            )
            return None
        
        state.status = status
        state.updated_at = datetime.utcnow()
        
        # 更新时间戳
        if status == "running" and not state.start_time:
            state.start_time = datetime.utcnow()
        elif status in ("success", "error", "skipped"):
            state.end_time = datetime.utcnow()
        
        # 更新其他字段
        for key, value in kwargs.items():
            if hasattr(state, key):
                setattr(state, key, value)
        
        self.session.add(state)
        self.session.commit()
        self.session.refresh(state)
        
        return state
    
    def save_node_inputs(
        self,
        run_id: int,
        node_id: str,
        inputs: Dict[str, Any]
    ) -> None:
        """保存节点输入"""
        stmt = select(NodeExecutionState).where(
            NodeExecutionState.run_id == run_id,
            NodeExecutionState.node_id == node_id
        )
        state = self.session.exec(stmt).first()
        
        if state:
            state.inputs_json = inputs
            self.session.add(state)
            self.session.commit()
    
    def save_node_outputs(
        self,
        run_id: int,
        node_id: str,
        outputs: Dict[str, Any]
    ) -> None:
        """保存节点输出"""
        stmt = select(NodeExecutionState).where(
            NodeExecutionState.run_id == run_id,
            NodeExecutionState.node_id == node_id
        )
        state = self.session.exec(stmt).first()
        
        if state:
            state.outputs_json = outputs
            self.session.add(state)
            self.session.commit()
    
    def add_node_log(
        self,
        run_id: int,
        node_id: str,
        level: str,
        message: str,
        **kwargs
    ) -> None:
        """添加节点日志"""
        stmt = select(NodeExecutionState).where(
            NodeExecutionState.run_id == run_id,
            NodeExecutionState.node_id == node_id
        )
        state = self.session.exec(stmt).first()
        
        if state:
            logs = state.logs_json or []
            logs.append({
                "level": level,
                "message": message,
                "timestamp": datetime.utcnow().isoformat(),
                **kwargs
            })
            state.logs_json = logs
            self.session.add(state)
            self.session.commit()
    
    def get_node_state(
        self,
        run_id: int,
        node_id: str
    ) -> Optional[NodeExecutionState]:
        """获取节点状态"""
        stmt = select(NodeExecutionState).where(
            NodeExecutionState.run_id == run_id,
            NodeExecutionState.node_id == node_id
        )
        return self.session.exec(stmt).first()
    
    def get_all_node_states(self, run_id: int) -> list[NodeExecutionState]:
        """获取运行的所有节点状态"""
        stmt = select(NodeExecutionState).where(
            NodeExecutionState.run_id == run_id
        )
        return list(self.session.exec(stmt).all())
    
    # ==================== 补偿日志（用于回滚）====================
    
    def add_compensation_log(
        self,
        run_id: int,
        operation: str,
        **data
    ) -> None:
        """添加补偿日志（用于回滚操作）
        
        Args:
            run_id: 运行ID
            operation: 操作类型（如 card.created, card.updated）
            **data: 操作相关数据
        """
        run = self.session.get(WorkflowRun, run_id)
        if not run:
            return
        
        logs = run.compensation_log or []
        logs.append({
            "operation": operation,
            "timestamp": datetime.utcnow().isoformat(),
            **data
        })
        run.compensation_log = logs
        self.session.add(run)
        self.session.commit()
