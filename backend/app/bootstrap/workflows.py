"""工作流初始化

从文件系统加载工作流定义并初始化到数据库。
"""

import os
import json
from sqlmodel import Session, select
from loguru import logger

from app.db.models import Workflow, WorkflowTrigger
from app.core.config import settings
from .registry import initializer
from app.services.workflow.registry import get_registered_nodes


def _extract_trigger_from_dsl(dsl: dict) -> tuple[str | None, dict | None]:
    """从 DSL 节点中提取触发器信息 (动态查找)"""
    nodes = dsl.get("nodes", [])
    registry = get_registered_nodes()
    
    for node in nodes:
        node_type = node.get("type")
        node_cls = registry.get(node_type)
        
        # 仅处理触发器类别的节点
        if node_cls and getattr(node_cls, "category", "") == "trigger":
            if hasattr(node_cls, "extract_trigger_info"):
                return node_cls.extract_trigger_info(node.get("config", {}))
                
    return None, None

def _parse_workflow_file(file_path: str) -> dict:
    """解析单个工作流文件"""
    with open(file_path, 'r', encoding='utf-8') as f:
        dsl = json.load(f)
    
    # 从 DSL 中提取基本信息
    name = dsl.get("name", os.path.splitext(os.path.basename(file_path))[0])
    description = dsl.get("description", f"内置工作流: {name}")
    keep_run_history = dsl.get("keep_run_history", False)
    
    # 提取触发器配置
    trigger_card_type, trigger_filter = _extract_trigger_from_dsl(dsl)

    return {
        "name": name,
        "description": description,
        "dsl": dsl,
        "keep_run_history": keep_run_history,
        "trigger_card_type": trigger_card_type,
        "trigger_filter": trigger_filter
    }

def _create_or_update_workflow(session: Session, name: str, description: str, dsl: dict, 
                               trigger_card_type: str | None, trigger_filter: dict | None, 
                               keep_run_history: bool, overwrite: bool) -> tuple[int, int, int]:
    """创建或更新单个工作流及其触发器"""
    created_count = updated_count = skipped_count = 0
    
    wf = session.exec(select(Workflow).where(Workflow.name == name)).first()
    if not wf:
        wf = Workflow(
            name=name, 
            description=description, 
            is_built_in=True, 
            is_active=True, 
            version=1, 
            dsl_version=1, 
            definition_json=dsl,
            keep_run_history=keep_run_history
        )
        session.add(wf)
        session.commit()
        session.refresh(wf)
        created_count += 1
        logger.info(f"已创建内置工作流: {name} (id={wf.id})")
    else:
        if overwrite:
            wf.definition_json = dsl
            wf.description = description
            wf.is_built_in = True
            wf.is_active = True
            wf.version = 1
            wf.keep_run_history = keep_run_history
            session.add(wf)
            session.commit()
            updated_count += 1
            logger.info(f"已更新内置工作流: {name} (id={wf.id})")
        else:
            skipped_count += 1
            
    # ... (trigger handling remains same) ...
    return created_count, updated_count, skipped_count

# Update call site in init_workflows
# (Implicitly handled by surrounding context if I replace carefully, but need to be precise)
    
    # 处理触发器（如果有）
    if trigger_card_type:
        # 确定触发器类型
        if trigger_card_type == "__project_created__":
            trigger_on = "onprojectcreate"
            card_type_name = None
        else:
            trigger_on = "onsave"
            card_type_name = trigger_card_type
        
        # 查找现有触发器
        tg = session.exec(
            select(WorkflowTrigger).where(
                WorkflowTrigger.workflow_id == wf.id,
                WorkflowTrigger.trigger_on == trigger_on
            )
        ).first()
        
        if not tg:
            tg = WorkflowTrigger(
                workflow_id=wf.id, 
                trigger_on=trigger_on, 
                card_type_name=card_type_name, 
                filter_json=trigger_filter,
                is_active=True
            )
            session.add(tg)
            session.commit()
            created_count += 1
            logger.info(f"已创建触发器: {trigger_on} -> {name}")
        else:
            if overwrite:
                tg.card_type_name = card_type_name
                tg.filter_json = trigger_filter
                tg.is_active = True
                session.add(tg)
                session.commit()
                updated_count += 1
                logger.info(f"已更新触发器: {trigger_on} -> {name}")
            else:
                skipped_count += 1
    
    return created_count, updated_count, skipped_count


def get_all_workflow_files() -> dict:
    """从文件系统加载所有工作流
    
    Returns:
        工作流字典，key为工作流名称
    """
    workflow_dir = os.path.join(os.path.dirname(__file__), 'workflows')
    if not os.path.exists(workflow_dir):
        logger.warning(f"Workflow directory not found at {workflow_dir}. Cannot load workflows.")
        return {}

    workflow_files = {}
    for filename in os.listdir(workflow_dir):
        if filename.endswith('.json'):
            file_path = os.path.join(workflow_dir, filename)
            try:
                workflow_data = _parse_workflow_file(file_path)
                name = workflow_data["name"]
                workflow_files[name] = workflow_data
            except Exception as e:
                logger.error(f"Failed to parse workflow file {filename}: {e}")
                continue
    
    return workflow_files

@initializer(name="工作流", order=50)
def init_workflows(session: Session) -> None:
    """初始化内置工作流
    
    从 bootstrap/workflows/ 目录加载所有 .json 文件并创建工作流及触发器。
    行为受配置项 BOOTSTRAP_OVERWRITE 控制。
    
    Args:
        session: 数据库会话
    """
    overwrite = settings.bootstrap.should_overwrite
    total_created = total_updated = total_skipped = 0
    
    # 加载所有工作流文件
    all_workflows = get_all_workflow_files()
    
    if not all_workflows:
        logger.warning("未找到任何工作流定义文件")
        return
    
    # 逐个处理工作流
    for name, workflow_data in all_workflows.items():
        try:
            c, u, s = _create_or_update_workflow(
                session,
                name=workflow_data["name"],
                description=workflow_data["description"],
                dsl=workflow_data["dsl"],
                trigger_card_type=workflow_data["trigger_card_type"],
                trigger_filter=workflow_data.get("trigger_filter"),
                keep_run_history=workflow_data.get("keep_run_history", False),
                overwrite=overwrite
            )
            total_created += c
            total_updated += u
            total_skipped += s
        except Exception as e:
            logger.error(f"初始化工作流 {name} 失败: {e}")
            continue
            
    if total_created > 0 or total_updated > 0:
        logger.info(f"工作流初始化完成: +{total_created}, ~{total_updated}, -{total_skipped}")
    else:
        logger.info(f"所有工作流已是最新 (skip={total_skipped})")
