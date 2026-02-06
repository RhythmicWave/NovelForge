"""统一的执行状态管理

职责：
- 统一管理执行上下文、节点状态、检查点
- 提供统一的加载和保存接口
- 确保状态一致性
"""

from dataclasses import dataclass
from typing import Dict, Any, Set, Optional
from datetime import datetime
from sqlmodel import Session, select
from loguru import logger

from app.db.models import NodeExecutionState


@dataclass
class CheckpointData:
    """检查点数据"""
    percent: float
    message: str
    data: Optional[Dict[str, Any]]
    timestamp: datetime


@dataclass
class NodeState:
    """节点状态"""
    node_id: str
    node_type: str
    status: str  # idle, running, success, error, paused
    progress: float
    outputs: Optional[Dict[str, Any]]
    checkpoint: Optional[CheckpointData]
    error: Optional[str]


class ExecutionState:
    """统一的执行状态
    
    职责：
    - 管理所有执行状态（上下文、节点状态、检查点）
    - 提供统一的加载和保存接口
    - 确保状态一致性
    
    使用示例：
        # 加载状态
        state = ExecutionState.load(run_id, session)
        
        # 更新节点状态
        state.update_node_state(
            node_id="task_a",
            node_type="Example.Process",
            status="running",
            progress=50.0
        )
        
        # 保存状态
        state.save(session)
    """
    
    def __init__(self, run_id: int):
        self.run_id = run_id
        self.context: Dict[str, Any] = {}  # 执行上下文（变量值）
        self.completed_nodes: Set[str] = set()  # 已完成的节点
        self.node_states: Dict[str, NodeState] = {}  # 节点状态
    
    @classmethod
    def load(cls, run_id: int, session: Session) -> 'ExecutionState':
        """从数据库加载完整状态
        
        Args:
            run_id: 运行 ID
            session: 数据库会话
            
        Returns:
            ExecutionState 实例
        """
        state = cls(run_id)
        
        # 加载所有节点状态
        stmt = select(NodeExecutionState).where(
            NodeExecutionState.run_id == run_id
        )
        db_states = session.exec(stmt).all()
        
        if not db_states:
            logger.info(f"[ExecutionState] 没有找到节点状态: run_id={run_id}")
            return state
        
        logger.info(f"[ExecutionState] 加载节点状态: run_id={run_id}, 节点数={len(db_states)}")
        
        for db_state in db_states:
            # 构建检查点数据
            checkpoint = None
            if db_state.checkpoint_json:
                checkpoint = CheckpointData(
                    percent=db_state.checkpoint_json.get('percent', 0.0),
                    message=db_state.checkpoint_json.get('message', ''),
                    data=db_state.checkpoint_json.get('data'),
                    timestamp=datetime.fromisoformat(
                        db_state.checkpoint_json.get('timestamp', datetime.utcnow().isoformat())
                    )
                )
            
            # 构建节点状态
            node_state = NodeState(
                node_id=db_state.node_id,
                node_type=db_state.node_type,
                status=db_state.status,
                progress=db_state.progress or 0.0,
                outputs=db_state.outputs_json,
                checkpoint=checkpoint,
                error=db_state.error_message
            )
            
            state.node_states[db_state.node_id] = node_state
            
            # 详细日志：记录每个节点的状态和输出
            logger.info(
                f"[ExecutionState] 加载节点: {db_state.node_id}, "
                f"status={db_state.status}, "
                f"has_outputs={db_state.outputs_json is not None}, "
                f"outputs_keys={list(db_state.outputs_json.keys()) if db_state.outputs_json else []}"
            )
            
            # 恢复已完成节点（包括 success 和 skipped）
            if db_state.status in ("success", "skipped"):
                state.completed_nodes.add(db_state.node_id)
                if db_state.outputs_json:
                    state.context[db_state.node_id] = db_state.outputs_json
                    logger.info(
                        f"[ExecutionState] ✅ 恢复节点输出到上下文: {db_state.node_id} "
                        f"(status={db_state.status}, outputs={db_state.outputs_json})"
                    )
                else:
                    logger.warning(
                        f"[ExecutionState] ⚠️ 节点状态为 {db_state.status} 但 outputs_json 为 None: {db_state.node_id}"
                    )
        
        logger.info(
            f"[ExecutionState] 状态加载完成: run_id={run_id}, "
            f"已完成={len(state.completed_nodes)}个节点, "
            f"上下文变量={list(state.context.keys())}"
        )
        
        return state
    
    def save(self, session: Session):
        """保存完整状态到数据库
        
        批量保存所有节点状态，减少数据库操作。
        
        Args:
            session: 数据库会话
        """
        if not self.node_states:
            return
        
        for node_id, node_state in self.node_states.items():
            # 查找或创建节点状态记录
            stmt = select(NodeExecutionState).where(
                NodeExecutionState.run_id == self.run_id,
                NodeExecutionState.node_id == node_id
            )
            db_state = session.exec(stmt).first()
            
            if not db_state:
                db_state = NodeExecutionState(
                    run_id=self.run_id,
                    node_id=node_id,
                    node_type=node_state.node_type
                )
            
            # 更新状态
            db_state.status = node_state.status
            db_state.progress = node_state.progress
            db_state.outputs_json = node_state.outputs  # 保存输出用于断点续传
            db_state.error_message = node_state.error
            db_state.updated_at = datetime.utcnow()
            
            # 更新时间戳
            if node_state.status == "running" and not db_state.start_time:
                db_state.start_time = datetime.utcnow()
            elif node_state.status in ("success", "error", "paused"):
                if not db_state.end_time:
                    db_state.end_time = datetime.utcnow()
            
            # 更新检查点
            if node_state.checkpoint:
                db_state.checkpoint_json = {
                    'percent': node_state.checkpoint.percent,
                    'message': node_state.checkpoint.message,
                    'data': node_state.checkpoint.data,
                    'timestamp': node_state.checkpoint.timestamp.isoformat()
                }
            
            session.add(db_state)
        
        session.commit()
        logger.debug(f"[ExecutionState] 状态已保存: run_id={self.run_id}, 节点数={len(self.node_states)}")
    
    def get_node_state(self, node_id: str) -> Optional[NodeState]:
        """获取节点状态
        
        Args:
            node_id: 节点 ID
            
        Returns:
            节点状态，如果不存在返回 None
        """
        return self.node_states.get(node_id)
    
    def update_node_state(
        self,
        node_id: str,
        node_type: str,
        status: str,
        progress: float = 0.0,
        outputs: Optional[Dict[str, Any]] = None,
        checkpoint: Optional[CheckpointData] = None,
        error: Optional[str] = None
    ):
        """更新节点状态
        
        Args:
            node_id: 节点 ID
            node_type: 节点类型
            status: 状态
            progress: 进度（0-100）
            outputs: 输出数据
            checkpoint: 检查点数据
            error: 错误信息
        """
        if node_id not in self.node_states:
            # 创建新状态
            self.node_states[node_id] = NodeState(
                node_id=node_id,
                node_type=node_type,
                status=status,
                progress=progress,
                outputs=outputs,
                checkpoint=checkpoint,
                error=error
            )
        else:
            # 更新现有状态
            node_state = self.node_states[node_id]
            node_state.status = status
            node_state.progress = progress
            if outputs is not None:
                node_state.outputs = outputs
            if checkpoint is not None:
                node_state.checkpoint = checkpoint
            if error is not None:
                node_state.error = error
        
        # 更新已完成列表和上下文
        if status == "success":
            self.completed_nodes.add(node_id)
            if outputs:
                self.context[node_id] = outputs
    
    def is_completed(self, node_id: str) -> bool:
        """检查节点是否已完成
        
        Args:
            node_id: 节点 ID
            
        Returns:
            是否已完成
        """
        return node_id in self.completed_nodes
    
    def get_checkpoint(self, node_id: str) -> Optional[CheckpointData]:
        """获取节点检查点
        
        Args:
            node_id: 节点 ID
            
        Returns:
            检查点数据，如果不存在返回 None
        """
        node_state = self.node_states.get(node_id)
        return node_state.checkpoint if node_state else None
    
    def clear_node_states(self, session: Session):
        """清理所有节点状态
        
        在开始新的运行前调用，确保没有旧数据干扰。
        
        Args:
            session: 数据库会话
        """
        stmt = select(NodeExecutionState).where(
            NodeExecutionState.run_id == self.run_id
        )
        old_states = session.exec(stmt).all()
        
        for state in old_states:
            session.delete(state)
        
        if old_states:
            session.commit()
            logger.info(f"[ExecutionState] 清理了 {len(old_states)} 个旧节点状态: run_id={self.run_id}")
        
        # 清空内存状态
        self.node_states.clear()
        self.completed_nodes.clear()
        self.context.clear()
