"""应用启动初始化

统一的启动初始化流程。
"""

from sqlmodel import Session
from loguru import logger

from app.db.models import SQLModel
from app.db.session import engine
from app.bootstrap.registry import discover_and_run_initializers
from app.core.events import discover_event_handlers
from app.services.workflow.registry import discover_workflow_nodes

def init_database():
    """初始化数据库表结构
    
    开发阶段可用；生产环境建议通过 Alembic 迁移。
    """
    logger.info("[启动] 初始化数据库表结构...")
    SQLModel.metadata.create_all(engine)
    logger.info("[启动] 数据库表结构初始化完成")


def init_application_data():
    """初始化应用数据
    
    自动发现并执行所有已注册的初始化器。
    初始化器通过 @initializer 装饰器注册，按 order 顺序执行。
    """
    logger.info("[启动] 初始化应用数据...")
    
    with Session(engine) as session:
        # 自动发现并执行所有初始化器
        discover_and_run_initializers(session)
    
    logger.info("[启动] 应用数据初始化完成")


def register_event_handlers():
    """注册事件处理器
    
    自动发现并导入所有事件处理器模块以触发@on_event装饰器。
    """
    logger.info("[启动] 注册事件处理器...")
    
    # 导入事件处理器模块以触发装饰器注册
    import app.services  # noqa: F401
    
    discover_event_handlers()
    logger.info("[启动] 事件处理器注册完成")


def register_workflow_nodes():
    """注册工作流节点
    
    自动发现并导入所有工作流节点模块以触发@register_node装饰器。
    """
    logger.info("[启动] 注册工作流节点...")
    discover_workflow_nodes()
    logger.info("[启动] 工作流节点注册完成")


def cleanup_zombie_runs():
    """清理死机运行
    
    将所有状态为 "running" 的运行标记为 "failed"。
    这些运行可能是因为服务器崩溃或重启而中断的。
    """
    logger.info("[启动] 清理死机运行...")
    
    from sqlmodel import select
    from app.db.models import WorkflowRun
    
    with Session(engine) as session:
        # 查找所有运行中的任务
        stmt = select(WorkflowRun).where(WorkflowRun.status == "running")
        zombie_runs = session.exec(stmt).all()
        
        if zombie_runs:
            logger.warning(f"[启动] 发现 {len(zombie_runs)} 个死机工作流运行，正在清理...")
            for run in zombie_runs:
                run.status = "failed"
                if not run.error_json:
                    run.error_json = {"error": "服务器重启，运行中断"}
                session.add(run)
                logger.info(f"[启动] 清理死机运行: run_id={run.id}, workflow_id={run.workflow_id}")
            
            session.commit()
            logger.info(f"[启动] 已清理 {len(zombie_runs)} 个死机工作流运行")
        else:
            logger.info("[启动] 没有发现死机工作流运行")
    
    logger.info("[启动] 死机工作流运行清理完成")


def startup():
    """应用启动入口
    
    执行所有启动初始化任务。
    """
    logger.info("=" * 50)
    logger.info("NovelForge 后端启动中...")
    logger.info("=" * 50)
    
    # 1. 初始化数据库
    init_database()
    
    # 2. 初始化应用数据
    init_application_data()
    
    # 3. 注册事件处理器
    register_event_handlers()
    
    # 4. 注册工作流节点
    register_workflow_nodes()
    
    # 5. 清理死机运行
    cleanup_zombie_runs()
    
    logger.info("=" * 50)
    logger.info("NovelForge 后端启动完成！")
    logger.info("=" * 50)


def shutdown():
    """应用关闭清理
    
    执行关闭时的清理任务（如有需要）。
    """
    logger.info("NovelForge 后端正在关闭...")
    # 可以在这里添加清理逻辑
    logger.info("NovelForge 后端已关闭")
