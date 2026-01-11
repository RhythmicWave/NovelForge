"""工作流触发器（装饰器注册版）

使用事件系统实现工作流触发。
"""

from typing import List, Dict
from sqlmodel import Session, select
from time import monotonic

from app.db.models import WorkflowTrigger, Card, Workflow, WorkflowRun
from app.services.workflow_engine import engine as wf_engine
from app.core import on_event, Event
from loguru import logger


# 防抖相关
_recent_keys: Dict[str, float] = {}
_DEBOUNCE_MS = 1500  # 同一 key 在该时间窗内不再触发


def _make_idempotency_key(event: str, workflow_id: int, card: Card | None, project_id: int | None) -> str:
    """生成幂等键
    
    Args:
        event: 事件名称
        workflow_id: 工作流ID
        card: 卡片对象
        project_id: 项目ID
        
    Returns:
        幂等键
    """
    card_id = getattr(card, "id", None) or 0
    proj_id = project_id or getattr(card, "project_id", None) or 0
    return f"evt:{event}|wf:{workflow_id}|card:{card_id}|proj:{proj_id}"


def _should_suppress(session: Session, key: str, workflow_id: int) -> bool:
    """检查是否应该抑制触发（防抖）
    
    Args:
        session: 数据库会话
        key: 幂等键
        workflow_id: 工作流ID
        
    Returns:
        是否应该抑制
    """
    # 1) 进程内防抖
    now = monotonic()
    last = _recent_keys.get(key)
    if last is not None and (now - last) * 1000 < _DEBOUNCE_MS:
        return True
    
    # 清理过期项，避免泄漏
    try:
        for k, v in list(_recent_keys.items()):
            if (now - v) * 1000 > 60000:
                _recent_keys.pop(k, None)
    except Exception:
        pass
    
    # 2) 持久层"同运行周期不二次触发"：查找相同幂等键且仍在进行的运行
    existing = session.exec(
        select(WorkflowRun).where(
            WorkflowRun.workflow_id == workflow_id,
            WorkflowRun.idempotency_key == key,
            WorkflowRun.status.in_(["queued", "running"]),  # type: ignore[arg-type]
        )
    ).first()
    if existing:
        return True
    
    # 标记本次
    _recent_keys[key] = now
    return False


def _match_triggers_for_card(session: Session, event: str, card: Card) -> List[WorkflowTrigger]:
    """匹配卡片相关的触发器
    
    Args:
        session: 数据库会话
        event: 事件名称
        card: 卡片对象
        
    Returns:
        匹配的触发器列表
    """
    q = select(WorkflowTrigger).where(
        WorkflowTrigger.trigger_on == event,
        WorkflowTrigger.is_active == True,  # noqa: E712
    )
    triggers = session.exec(q).all()
    
    # 确保 card_type 关系已加载
    if card.card_type is None and card.card_type_id:
        session.refresh(card, ["card_type"])
    
    card_type_name = card.card_type.name if card.card_type else None
    
    matched: List[WorkflowTrigger] = []
    for t in triggers:
        # 过滤 card_type
        if t.card_type_name:
            if not card_type_name or card_type_name != t.card_type_name:
                continue
        # filter_json 预留：当前不实现复杂匹配
        matched.append(t)
    return matched


def _execute_triggers(session: Session, event_name: str, triggers: List[WorkflowTrigger], 
                     scope: Dict, card: Card | None = None, project_id: int | None = None) -> List[int]:
    """执行触发器
    
    Args:
        session: 数据库会话
        event_name: 事件名称
        triggers: 触发器列表
        scope: 作用域
        card: 卡片对象
        project_id: 项目ID
        
    Returns:
        运行ID列表
    """
    run_ids: List[int] = []
    for t in triggers:
        wf = session.get(Workflow, t.workflow_id)
        if not wf or not wf.is_active:
            continue
        
        idem_key = _make_idempotency_key(event_name, int(t.workflow_id), card, project_id)
        if _should_suppress(session, idem_key, int(t.workflow_id)):
            continue
        
        run = wf_engine.create_run(
            session=session,
            workflow=wf,
            scope_json=scope,
            params_json={},
            idempotency_key=idem_key,
        )
        wf_engine.run(session, run)
        if run.id:
            run_ids.append(int(run.id))
    
    return run_ids


@on_event("card.saved")
def handle_card_saved(event: Event):
    """处理卡片保存事件
    
    Args:
        event: 事件对象
    """
    session: Session = event.data.get("session")
    card: Card = event.data.get("card")
    
    if not session or not card:
        logger.warning("[工作流触发] card.saved 事件缺少必要数据")
        return
    
    triggers = _match_triggers_for_card(session, "onsave", card)
    scope = {"card_id": card.id, "project_id": card.project_id}
    run_ids = _execute_triggers(session, "onsave", triggers, scope, card, card.project_id)
    
    # 将运行ID列表写回事件数据，供API层使用
    event.data["triggered_run_ids"] = run_ids
    
    logger.info(f"[工作流触发] card.saved - 触发了 {len(run_ids)} 个工作流，运行ID: {run_ids}")


@on_event("generate.finished")
def handle_generate_finished(event: Event):
    """处理生成完成事件
    
    Args:
        event: 事件对象
    """
    session: Session = event.data.get("session")
    card: Card | None = event.data.get("card")
    project_id: int | None = event.data.get("project_id")
    
    if not session:
        logger.warning("[工作流触发] generate.finished 事件缺少session")
        return
    
    q = select(WorkflowTrigger).where(
        WorkflowTrigger.trigger_on == "ongenfinish",
        WorkflowTrigger.is_active == True,  # noqa: E712
    )
    triggers = session.exec(q).all()
    
    # 过滤卡片类型
    if card:
        filtered_triggers = []
        for t in triggers:
            if t.card_type_name and card.card_type and card.card_type.name != t.card_type_name:
                continue
            filtered_triggers.append(t)
        triggers = filtered_triggers
    
    scope = {"project_id": project_id}
    if card and card.id:
        scope["card_id"] = card.id
    
    run_ids = _execute_triggers(session, "ongenfinish", triggers, scope, card, project_id)
    logger.info(f"[工作流触发] generate.finished - 触发了 {len(run_ids)} 个工作流")


@on_event("project.created")
def handle_project_created(event: Event):
    """处理项目创建事件
    
    Args:
        event: 事件对象
    """
    session: Session = event.data.get("session")
    project_id: int = event.data.get("project_id")
    
    if not session or not project_id:
        logger.warning("[工作流触发] project.created 事件缺少必要数据")
        return
    
    triggers = session.exec(
        select(WorkflowTrigger).where(
            WorkflowTrigger.trigger_on == "onprojectcreate",
            WorkflowTrigger.is_active == True,
        )
    ).all()
    
    scope = {"project_id": project_id}
    run_ids = _execute_triggers(session, "onprojectcreate", triggers, scope, None, project_id)
    
    logger.info(f"[工作流触发] project.created - 触发了 {len(run_ids)} 个工作流")


