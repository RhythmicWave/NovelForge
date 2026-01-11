"""应用启动初始化

统一的启动初始化流程。
"""

from sqlmodel import Session
from loguru import logger


def init_database():
    """初始化数据库表结构
    
    开发阶段可用；生产环境建议通过 Alembic 迁移。
    """
    from app.db.models import SQLModel
    from app.db.session import engine
    
    logger.info("[启动] 初始化数据库表结构...")
    SQLModel.metadata.create_all(engine)
    logger.info("[启动] 数据库表结构初始化完成")


def init_application_data():
    """初始化应用数据
    
    自动发现并执行所有已注册的初始化器。
    初始化器通过 @initializer 装饰器注册，按 order 顺序执行。
    """
    from app.db.session import engine
    from app.bootstrap.registry import discover_and_run_initializers
    
    logger.info("[启动] 初始化应用数据...")
    
    with Session(engine) as session:
        # 自动发现并执行所有初始化器
        discover_and_run_initializers(session)
    
    logger.info("[启动] 应用数据初始化完成")


def register_event_handlers():
    """注册事件处理器
    
    自动发现并导入所有事件处理器模块以触发@on_event装饰器。
    """
    from app.core.events import discover_event_handlers
    
    logger.info("[启动] 注册事件处理器...")
    discover_event_handlers()
    logger.info("[启动] 事件处理器注册完成")


def register_workflow_nodes():
    """注册工作流节点
    
    自动发现并导入所有工作流节点模块以触发@register_node装饰器。
    """
    from app.services.workflow.registry import discover_workflow_nodes
    
    logger.info("[启动] 注册工作流节点...")
    discover_workflow_nodes()
    logger.info("[启动] 工作流节点注册完成")


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
