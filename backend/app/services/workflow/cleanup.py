from datetime import datetime, timedelta
from sqlmodel import Session, select, delete
from loguru import logger
from app.db.models import WorkflowRun, Workflow
from app.core.config import settings

def cleanup_expired_runs(session: Session, transient_retention_minutes: int = None, persistent_retention_days: int = None):
    """清理过期的工作流运行记录
    
    策略：
    1. Transient (keep_run_history=False): 完成后保留 N 分钟（用于前端查看状态），然后删除。
    2. Persistent (keep_run_history=True): 保留 N 天。
    3. 状态未完成（running/queued）的运行不删除，以免误杀正在执行的任务。
    """
    if transient_retention_minutes is None:
        transient_retention_minutes = settings.workflow.retention_transient_minutes
    if persistent_retention_days is None:
        persistent_retention_days = settings.workflow.retention_persistent_days
        
    now = datetime.utcnow()
    deleted_count = 0
    
    try:
        # 1. 查询所有已完成的运行
        # 注意：这里需要 join Workflow 表来获取 keep_run_history 字段
        # 但 SQLModel delete 语句 join 比较麻烦，我们先查出 ID
        
        # 策略 A: 查找 "非持久化" 且 "已完成" 且 "完成时间 > 10分钟前" 的
        transient_cutoff = now - timedelta(minutes=transient_retention_minutes)
        
        # 查找符合条件的 transient runs
        # Workflow.keep_run_history == False OR NULL
        stmt_transient = (
            select(WorkflowRun.id)
            .join(Workflow)
            .where(
                WorkflowRun.status.in_(["succeeded", "failed", "cancelled", "timeout"]),
                WorkflowRun.finished_at < transient_cutoff,
                (Workflow.keep_run_history == False) | (Workflow.keep_run_history == None)
            )
        )
        transient_ids = session.exec(stmt_transient).all()
        
        if transient_ids:
            # 批量删除
            # 注意：WorkflowRun 有 cascade delete 到 NodeExecutionState，所以只需删 Run
            stmt_del = delete(WorkflowRun).where(WorkflowRun.id.in_(transient_ids))
            result = session.exec(stmt_del)
            deleted_count += result.rowcount if hasattr(result, 'rowcount') else len(transient_ids)
            logger.info(f"[Cleanup] 清理临时运行记录: {len(transient_ids)} 条")

        # 策略 B: 查找 "持久化" 且 "已完成" 且 "完成时间 > 30天前" 的
        persistent_cutoff = now - timedelta(days=persistent_retention_days)
        stmt_persistent = (
            select(WorkflowRun.id)
            .join(Workflow)
            .where(
                WorkflowRun.status.in_(["succeeded", "failed", "cancelled", "timeout"]),
                WorkflowRun.finished_at < persistent_cutoff,
                Workflow.keep_run_history == True
            )
        )
        persistent_ids = session.exec(stmt_persistent).all()
        
        if persistent_ids:
            stmt_del = delete(WorkflowRun).where(WorkflowRun.id.in_(persistent_ids))
            result = session.exec(stmt_del)
            count = result.rowcount if hasattr(result, 'rowcount') else len(persistent_ids)
            deleted_count += count
            logger.info(f"[Cleanup] 清理过期持久化记录: {count} 条")
            
        session.commit()
        if deleted_count > 0:
            logger.info(f"[Cleanup] 工作流清理完成，共删除 {deleted_count} 条记录")
            
    except Exception as e:
        logger.error(f"[Cleanup] 清理工作流失败: {e}")
        session.rollback()
