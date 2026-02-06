"""触发器提取器 - 从工作流代码中自动提取触发器配置

用于优化触发器系统，避免单独的 WorkflowTrigger 表查询。
"""

from typing import List, Dict, Any
from loguru import logger


def extract_triggers_from_code(code: str) -> List[Dict[str, Any]]:
    """从工作流代码中提取触发器配置
    
    解析代码中的触发器节点，提取触发器信息并缓存到 Workflow.triggers_cache 字段。
    
    支持的触发器节点：
        - Trigger.ProjectCreated: 项目创建触发器
          参数: template (可选)
          
        - Trigger.CardSaved: 卡片保存触发器
          参数: card_type (可选), on_create (默认true), on_update (默认true)
    
    Args:
        code: 工作流代码（XML 格式）
        
    Returns:
        触发器配置列表，格式：
        [
            {
                "event": "project.created",
                "match": {"template": "snowflake"}  # 从节点参数构建
            },
            ...
        ]
    
    Example:
        >>> code = '''
        ... <node name="trigger">
        ...   Trigger.ProjectCreated(template="snowflake")
        ... </node>
        ... '''
        >>> extract_triggers_from_code(code)
        [{"event": "project.created", "match": {"template": "snowflake"}}]
    """
    from app.services.workflow.parser.xml_parser import XMLWorkflowParser
    
    if not code or not code.strip():
        return []
    
    # 节点类型到事件名称的映射
    NODE_TYPE_TO_EVENT = {
        "Trigger.ProjectCreated": "project.created",
        "Trigger.CardSaved": "card.saved",
    }
    
    try:
        # 解析工作流代码
        parser = XMLWorkflowParser()
        plan = parser.parse(code)
        
        triggers = []
        
        # 遍历所有语句，查找触发器节点
        for stmt in plan.statements:
            # 跳过禁用的节点
            if stmt.disabled:
                logger.debug(f"[TriggerExtractor] 跳过禁用的触发器节点: {stmt.variable}")
                continue
            
            node_type = stmt.node_type
            config = stmt.config or {}
            
            # 检查是否是触发器节点
            event = NODE_TYPE_TO_EVENT.get(node_type)
            if not event:
                continue
            
            # 根据节点类型构建 match 条件
            match = {}
            
            if node_type == "Trigger.ProjectCreated":
                # 提取 template 参数
                if "template" in config and config["template"]:
                    match["template"] = config["template"]
                    
            elif node_type == "Trigger.CardSaved":
                # 提取 card_type 参数
                if "card_type" in config and config["card_type"]:
                    match["card_type"] = config["card_type"]
                # 提取 on_create 和 on_update 参数
                on_create = config.get("on_create", True)
                on_update = config.get("on_update", True)
                if not on_create:
                    match["is_created"] = False
                elif not on_update:
                    match["is_created"] = True
                # 如果两者都为 true，不添加 is_created 条件
            
            trigger_config = {
                "event": event,
                "match": match if match else None
            }
            
            triggers.append(trigger_config)
        
        logger.debug(f"[TriggerExtractor] 从代码中提取了 {len(triggers)} 个触发器")
        return triggers
    
    except Exception as e:
        logger.error(f"[TriggerExtractor] 提取触发器失败: {e}")
        return []


def sync_triggers_cache(workflow, session) -> None:
    """同步工作流的触发器缓存
    
    从 definition_code 中提取触发器，更新 triggers_cache 字段。
    
    Args:
        workflow: Workflow 对象
        session: 数据库会话
    """
    if not workflow.definition_code:
        workflow.triggers_cache = []
        return
    
    triggers = extract_triggers_from_code(workflow.definition_code)
    
    workflow.triggers_cache = triggers
    session.add(workflow)
    
    logger.info(f"[TriggerExtractor] 工作流 {workflow.id} ({workflow.name}) 的触发器缓存已更新: {len(triggers)} 个触发器")


def match_event(event_name: str, event_data: Dict[str, Any], trigger: Dict[str, Any]) -> bool:
    """判断事件是否匹配触发器
    
    Args:
        event_name: 事件名称（如 project.created, card.saved）
        event_data: 事件数据（如 {"project_id": 1, "template": "snowflake"}）
        trigger: 触发器配置（包含 event 和 match 字段）
        
    Returns:
        是否匹配
    """
    # 1. 事件名称必须匹配
    if trigger.get("event") != event_name:
        return False
    
    # 2. 如果没有 match 条件，直接匹配
    match_conditions = trigger.get("match")
    if not match_conditions:
        return True
    
    # 3. 检查所有 match 条件
    for key, expected_value in match_conditions.items():
        actual_value = event_data.get(key)
        
        # 简单相等匹配
        if actual_value != expected_value:
            return False
    
    return True


def get_active_triggers_by_event(session, event_name: str, event_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """获取匹配指定事件的触发器
    
    Args:
        session: 数据库会话
        event_name: 事件名称（如 project.created, card.saved）
        event_data: 事件数据（如 {"project_id": 1, "template": "snowflake"}）
        
    Returns:
        匹配的触发器列表，格式：
        [
            {
                "workflow_id": 1,
                "event": "project.created",
                "match": {"template": "snowflake"}
            },
            ...
        ]
    """
    from sqlmodel import select
    from app.db.models import Workflow
    
    # 查询所有激活的工作流
    stmt = select(Workflow).where(
        Workflow.is_active == True,
        Workflow.triggers_cache.isnot(None)
    )
    workflows = session.exec(stmt).all()
    
    matched_triggers = []
    
    for wf in workflows:
        if not wf.triggers_cache:
            continue
        
        for trigger in wf.triggers_cache:
            # 使用新的匹配逻辑
            if match_event(event_name, event_data, trigger):
                matched_triggers.append({
                    "workflow_id": wf.id,
                    **trigger
                })
    
    logger.debug(f"[TriggerExtractor] 找到 {len(matched_triggers)} 个匹配的触发器: event={event_name}, data={event_data}")
    return matched_triggers
