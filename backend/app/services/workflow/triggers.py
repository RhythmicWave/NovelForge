"""工作流触发器（装饰器注册版）

使用事件系统实现工作流触发。
"""

import asyncio
from typing import List, Dict, Any
from sqlmodel import Session, select
from time import monotonic
from loguru import logger

from app.db.models import WorkflowTrigger, Card, Workflow, WorkflowRun
from app.services.workflow.engine import (
    RunManager,
    GraphBuilder,
    WorkflowExecutor,
    StateManager
)
from app.services.workflow.types import WorkflowSettings
from app.db.session import engine as db_engine
from sqlmodel import Session
from app.core import on_event, Event

# 防抖相关
_recent_keys: Dict[str, float] = {}
_DEBOUNCE_MS = 1500  # 同一 key 在该时间窗内不再触发


def _make_idempotency_key(event: str, workflow_id: int, card: Card | None, project_id: int | None) -> str:
    """生成幂等键"""
    card_id = getattr(card, "id", None) or 0
    proj_id = project_id or getattr(card, "project_id", None) or 0
    return f"evt:{event}|wf:{workflow_id}|card:{card_id}|proj:{proj_id}"


def _should_suppress(session: Session, key: str, workflow_id: int) -> bool:
    """检查是否应该抑制触发（防抖）"""
    # 1) 进程内防抖
    now = monotonic()
    last = _recent_keys.get(key)
    if last is not None and (now - last) * 1000 < _DEBOUNCE_MS:
        return True
    
    # 清理过期项
    try:
        for k, v in list(_recent_keys.items()):
            if (now - v) * 1000 > 60000:
                _recent_keys.pop(k, None)
    except Exception:
        pass
    
    # 2. 持久层防抖
    # 查找是否存在正在运行或排队的相同任务
    # 增加时间检查：如果任务卡在 queued/running 超过 2 分钟，视为僵尸任务，允许重新触发
    from datetime import datetime, timedelta
    
    cutoff_time = datetime.utcnow() - timedelta(minutes=2)
    
    existing = session.exec(
        select(WorkflowRun).where(
            WorkflowRun.workflow_id == workflow_id,
            WorkflowRun.idempotency_key == key,
            WorkflowRun.status.in_(["queued", "running"]),
            WorkflowRun.created_at > cutoff_time # 只有最近活跃的才算冲突
        )
    ).first()
    
    if existing:
        logger.warning(f"[Trigger] Idempotency hit: Found active run {existing.id} (created at {existing.created_at})")
        return True
    
    _recent_keys[key] = now
    return False


def _get_value_by_path(obj: Any, path: str) -> Any:
    """通过点号路径获取对象属性值"""
    parts = path.split('.')
    current = obj
    
    for part in parts:
        if current is None:
            return None
            
        if isinstance(current, dict):
            current = current.get(part)
        else:
            current = getattr(current, part, None)
            
    return current


def _check_condition(value: Any, op: str, target: Any) -> bool:
    """检查单个条件"""
    if op == "eq" or op == "==":
        return value == target
    elif op == "neq" or op == "!=":
        return value != target
    elif op == "contains":
        if isinstance(value, (list, str, dict)):
            return target in value
        return False
    elif op == "not_contains":
        if isinstance(value, (list, str, dict)):
            return target not in value
        return True
    elif op == "gt" or op == ">":
        try:
            return float(value) > float(target)
        except (ValueError, TypeError):
            return False
    elif op == "lt" or op == "<":
        try:
            return float(value) < float(target)
        except (ValueError, TypeError):
            return False
    elif op == "exists":
        if target:  # If target is true, check if exists (not None)
            return value is not None
        else:      # If target is false, check if not exists (is None)
            return value is None
    # changed 操作符逻辑特殊，在 _evaluate_filter 中处理，这里的 fallback 只是为了安全
    return False


def _evaluate_filter(card: Card, filter_config: Dict, old_content: Dict | None = None) -> bool:
    """评估卡片是否满足过滤配置"""
    if not filter_config:
        return True
        
    conditions = filter_config.get("conditions", [])
    if not conditions:
        return True
        
    operator = filter_config.get("operator", "and").lower()
    results = []
    
    # 构造 old_obj 包装器以便使用相同的路径逻辑
    old_obj = {"content": old_content} if old_content else {}
    
    for cond in conditions:
        field = cond.get("field")
        op = cond.get("op", "eq")
        target = cond.get("value")
        
        if not field:
            continue
            
        value = _get_value_by_path(card, field)
        
        # 特殊处理 changed 操作符
        if op == "changed":
            old_value = _get_value_by_path(old_obj, field)
            # 如果是创建 (old_content is None)，视为 changed
            if old_content is None: 
                res = True
            else:
                res = value != old_value
        else:
            res = _check_condition(value, op, target)
            
        results.append(res)
        
        # 优化：如果是 AND 且有一个为 False，直接返回 False
        if operator == "and" and not res:
            return False
        # 优化：如果是 OR 且有一个为 True，直接返回 True
        if operator == "or" and res:
            return True
            
    if operator == "and":
        return all(results)
    else:  # or
        return any(results)


def _match_triggers_for_card(session: Session, event: str, card: Card, is_created: bool = False, old_content: Dict | None = None) -> List[WorkflowTrigger]:
    """匹配卡片相关的触发器"""
    q = select(WorkflowTrigger).where(
        WorkflowTrigger.trigger_on == event,
        WorkflowTrigger.is_active == True,  # noqa: E712
    )
    triggers = session.exec(q).all()
    
    if card.card_type is None and card.card_type_id:
        session.refresh(card, ["card_type"])
    
    card_type_name = card.card_type.name if card.card_type else None
    
    matched: List[WorkflowTrigger] = []
    current_event = "create" if is_created else "update"
    
    for t in triggers:
        # 1. 检查卡片类型 (如果是 None，则匹配所有类型)
        if t.card_type_name:
            if not card_type_name or card_type_name != t.card_type_name:
                continue
        
        # 检查过滤配置
        if t.filter_json:
            # 2. 检查细粒度事件类型 (create/update)
            if "events" in t.filter_json:
                allowed_events = t.filter_json["events"]
                if current_event not in allowed_events:
                    continue
            
            # 3. 检查条件过滤器
            if "conditions" in t.filter_json:
                if not _evaluate_filter(card, t.filter_json, old_content):
                    continue
                
        matched.append(t)
    return matched


def _async_execute_workflow(run_id: int):
    """异步执行工作流（在后台任务中）"""
    async def _execute():
        # logger.debug(f"[Trigger] 开始后台执行工作流: run_id={run_id}")
        session = Session(db_engine)
        try:
            # 1. 获取运行记录
            state_manager = StateManager(session)
            run = session.get(WorkflowRun, run_id)
            if not run:
                logger.error(f"[Trigger] 运行记录不存在: run_id={run_id}")
                return

            wf = session.get(Workflow, run.workflow_id)
            if not wf:
                logger.error(f"[Trigger] 工作流不存在: wf_id={run.workflow_id}")
                return

            # 2. 构建执行图
            graph_builder = GraphBuilder()
            # 兼容处理：优先使用 definition_json
            definition = wf.definition_json or {}
            graph = graph_builder.build(definition)

            # 3. 准备执行器
            executor = WorkflowExecutor(state_manager)
            
            # 4. 执行
            # 初始变量
            initial_vars = {}
            if run.scope_json:
                initial_vars.update(run.scope_json)
            if run.params_json:
                initial_vars.update(run.params_json)

            settings = WorkflowSettings() 
            
            # [Fix] 手动管理运行状态，因为这里为了保持 session 独立性没有使用 RunManager._execute_run
            state_manager.update_run_status(run_id, "running")
            
            try:
                result = await executor.execute(
                    run_id=run_id,
                    graph=graph,
                    settings=settings,
                    initial_variables=initial_vars
                )
                
                # [Fix] 执行成功后更新状态为 succeeded
                state_manager.update_run_status(
                    run_id, 
                    "succeeded",
                    summary_json={
                        "executed_nodes": result.get("executed_nodes", []),
                        "outputs": result.get("outputs", {})
                    }
                )
            except Exception as e:
                # [Fix] 执行失败更新状态
                state_manager.update_run_status(run_id, "failed")
                state_manager.save_error(run_id, str(e))
                raise
        except Exception as e:
            logger.exception(f"[Trigger] 后台执行失败: run_id={run_id}")
        finally:
            session.close()

    try:
        try:
            # Check if we are in a running loop (async context)
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # logger.debug(f"[Trigger] 在现有事件循环中调度后台任务: run_id={run_id}")
            loop.create_task(_execute())
        else:
            # logger.debug(f"[Trigger] 在同步上下文中执行（阻塞模式）: run_id={run_id}")
            # Use asyncio.run for sync context (e.g. threadpool)
            # functionality > latency for now
            asyncio.run(_execute())
            
    except Exception as e:
        logger.error(f"[Trigger] 无法调度后台任务: {e}")


def _execute_triggers(session: Session, event_name: str, triggers: List[WorkflowTrigger], 
                     scope: Dict, card: Card | None = None, project_id: int | None = None,
                     payload: Dict[str, Any] | None = None) -> List[int]:
    """执行触发器"""
    run_ids: List[int] = []
    
    run_manager = RunManager(session)
    # logger.debug(f"[Trigger] Processing {len(triggers)} triggers for event {event_name}")
    
    for t in triggers:
        wf = session.get(Workflow, t.workflow_id)
        if not wf:
            logger.warning(f"[Trigger] Workflow {t.workflow_id} not found")
            continue
        if not wf.is_active:
            # logger.debug(f"[Trigger] Workflow {t.workflow_id} is inactive")
            continue
        
        idem_key = _make_idempotency_key(event_name, int(t.workflow_id), card, project_id)
        if _should_suppress(session, idem_key, int(t.workflow_id)):
            logger.debug(f"[Trigger] Trigger suppressed by idempotency: {idem_key}")
            continue
        
        try:
            # 过滤掉不可序列化的对象
            serializable_payload = {}
            if payload:
                for key, value in payload.items():
                    if key in ['session', 'card']:
                        continue
                    if isinstance(value, (str, int, float, bool, list, dict, type(None))):
                        serializable_payload[key] = value
            
            # logger.debug(f"[Trigger] Creating run for workflow {t.workflow_id}")
            # 1. 创建运行记录 (使用当前 Session)
            run = run_manager.create_run(
                workflow_id=t.workflow_id,
                trigger_data=scope,
                params=serializable_payload,
                idempotency_key=idem_key
            )
            
            if run.id:
                run_ids.append(int(run.id))
                
                try:
                    from app.core.workflow_context import add_triggered_run_id
                    add_triggered_run_id(int(run.id))
                except Exception:
                    pass

                # logger.debug(f"[Trigger] Run created: {run.id}. Scheduling async exec.")
                # 2. 调度异步执行
                _async_execute_workflow(run.id)
            else:
                 logger.error(f"[Trigger] Run creation returned no ID for wf {t.workflow_id}")
                
        except Exception as e:
            logger.exception(f"[Trigger] 创建/触发运行失败: wf={t.workflow_id}, err={e}")

    return run_ids


@on_event("card.saved")
def handle_card_saved(event: Event):
    """处理卡片保存事件"""
    session: Session = event.data.get("session")
    card: Card = event.data.get("card")
    
    if not session or not card:
        logger.warning("[工作流触发] card.saved 事件缺少必要数据")
        return
    
    is_created = event.data.get("is_created", False)
    
    triggers = _match_triggers_for_card(session, "onsave", card, is_created=is_created)
    scope = {"card_id": card.id, "project_id": card.project_id}
    # 传递 event.data 作为 payload
    run_ids = _execute_triggers(session, "onsave", triggers, scope, card, card.project_id, payload=event.data)
    
    event.data["triggered_run_ids"] = run_ids
    if run_ids:
        logger.info(f"[工作流触发] card.saved - 触发了 {len(run_ids)} 个工作流")


@on_event("generate.finished")
def handle_generate_finished(event: Event):
    """处理生成完成事件"""
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
    
    run_ids = _execute_triggers(session, "ongenfinish", triggers, scope, card, project_id, payload=event.data)
    if run_ids:
        logger.info(f"[工作流触发] generate.finished - 触发了 {len(run_ids)} 个工作流")


@on_event("project.created")
def handle_project_created(event: Event):
    """处理项目创建事件"""
    try:
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
        run_ids = _execute_triggers(session, "onprojectcreate", triggers, scope, None, project_id, payload=event.data)
        
        event.data["triggered_run_ids"] = run_ids

        if run_ids:
            logger.info(f"[工作流触发] project.created - 触发了 {len(run_ids)} 个工作流")
    except Exception as e:
        logger.exception(f"[工作流] handle_project_created failed: {e}")
