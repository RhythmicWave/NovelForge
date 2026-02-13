"""工作流触发器

使用事件系统实现工作流触发。
只支持新的代码式工作流系统。

"""

import asyncio
from typing import List, Dict, Any
from sqlmodel import Session, select
from time import monotonic
from loguru import logger

from app.db.models import Card, Workflow, WorkflowRun
from app.services.workflow.engine import StateManager
from app.db.session import engine as db_engine
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
    """检查是否应该抑制触发（仅进程内防抖）
    
    只做短时间防抖（1.5秒），避免同一事件在极短时间内重复触发。
    不做持久层检查，允许失败的任务重新触发。
    """
    # 进程内防抖：1.5秒内不重复触发
    now = monotonic()
    last = _recent_keys.get(key)
    if last is not None and (now - last) * 1000 < _DEBOUNCE_MS:
        logger.debug(f"[Trigger] 防抖抑制: {key}")
        return True
    
    # 清理过期项（超过1分钟）
    try:
        for k, v in list(_recent_keys.items()):
            if (now - v) * 1000 > 60000:
                _recent_keys.pop(k, None)
    except Exception:
        pass
    
    # 记录本次触发
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


def _match_triggers_for_card(session: Session, event: str, card: Card, is_created: bool = False, old_content: Dict | None = None) -> List[Dict[str, Any]]:
    """匹配卡片相关的触发器（使用 triggers_cache）"""
    from app.services.workflow.trigger_extractor import get_active_triggers_by_event
    
    if card.card_type is None and card.card_type_id:
        session.refresh(card, ["card_type"])
    
    card_type_name = card.card_type.name if card.card_type else None

    # 从 triggers_cache 中获取触发器（性能优化）
    # 新版触发器匹配接口基于 event_name + event_data
    event_name = "card.saved" if event == "onsave" else event
    event_data = {
        "card_id": card.id,
        "project_id": card.project_id,
        "card_type": card_type_name,
        "is_created": bool(is_created),
    }
    all_triggers = get_active_triggers_by_event(session, event_name, event_data)
    
    matched: List[Dict[str, Any]] = []
    current_event = "create" if is_created else "update"
    
    for t in all_triggers:
        filter_json = t.get("filter_json")
        
        if filter_json:
            # 1. 检查细粒度事件类型 (create/update)
            if "events" in filter_json:
                allowed_events = filter_json["events"]
                if current_event not in allowed_events:
                    continue
            
            # 2. 检查条件过滤器
            if "conditions" in filter_json:
                if not _evaluate_filter(card, filter_json, old_content):
                    continue
                
        matched.append(t)
    return matched


def _async_execute_workflow(run_id: int):
    """异步执行工作流（在后台任务中）
    
    只支持代码式工作流系统。
    """
    async def _execute():
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
            
            # 2. 更新状态为运行中
            state_manager.update_run_status(run_id, "running")
            
            try:
                # 3. 执行代码式工作流
                await _execute_code_workflow(session, state_manager, run, wf)
                    
            except Exception as e:
                # 执行失败更新状态
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
            loop.create_task(_execute())
        else:
            # Use asyncio.run for sync context (e.g. threadpool)
            asyncio.run(_execute())
            
    except Exception as e:
        logger.error(f"[Trigger] 无法调度后台任务: {e}")


async def _execute_code_workflow(
    session: Session,
    state_manager: StateManager,
    run: WorkflowRun,
    workflow: Workflow,
) -> None:
    """执行代码式工作流（触发器专用）
    
    与 API 的流式执行不同，这里是后台执行，不需要推送事件。
    """
    from .engine.async_executor import AsyncExecutor
    from .parser.marker_parser import WorkflowParser
    
    run_id = run.id
    code = workflow.definition_code or ""
    
    if not code:
        raise ValueError("工作流缺少代码内容")
    
    logger.info(f"[Trigger] 解析代码式工作流: run_id={run_id}")
    
    # 解析代码
    parser = WorkflowParser()
    plan = parser.parse(code)
    
    logger.info(f"[Trigger] 执行代码式工作流: run_id={run_id}, 语句数={len(plan.statements)}")
    
    # 准备初始上下文（注入触发器数据）
    initial_context = {}
    
    # 将触发器数据注入到 __trigger_data__ 键
    # 触发器节点会从这里读取数据并输出
    trigger_data = {}
    if run.scope_json:
        trigger_data.update(run.scope_json)
    if run.params_json:
        trigger_data.update(run.params_json)
    
    if trigger_data:
        initial_context["__trigger_data__"] = trigger_data
    
    # 执行工作流（消费所有事件）
    executor = AsyncExecutor(
        session=session,
        state_manager=state_manager,
        run_id=run_id
    )
    
    # execute_stream 是一个异步生成器，需要消费所有事件
    async for event in executor.execute_stream(plan, initial_context):
        # 记录关键事件
        if event.type == "error":
            logger.error(f"[Trigger] 节点执行失败: {event.statement.variable if event.statement else 'unknown'}, error={event.error}")
        elif event.type == "complete":
            logger.debug(f"[Trigger] 节点执行完成: {event.statement.variable if event.statement else 'unknown'}")
    
    # 更新状态为成功
    state_manager.update_run_status(
        run_id,
        "succeeded",
        summary_json={
            "variables": list(executor.context.keys()),
            "outputs": executor.context
        }
    )
    
    logger.info(f"[Trigger] 工作流执行完成: run_id={run_id}")


def _execute_triggers(session: Session, event_name: str, triggers: List[Dict[str, Any]], 
                     scope: Dict, card: Card | None = None, project_id: int | None = None,
                     payload: Dict[str, Any] | None = None) -> List[int]:
    """执行触发器（使用 triggers_cache）"""
    from .engine import RunManager
    
    run_ids: List[int] = []
    
    run_manager = RunManager(session)
    
    for t in triggers:
        workflow_id = t.get("workflow_id")
        if not workflow_id:
            continue
            
        wf = session.get(Workflow, workflow_id)
        if not wf:
            logger.warning(f"[Trigger] Workflow {workflow_id} not found")
            continue
        if not wf.is_active:
            continue
        
        idem_key = _make_idempotency_key(event_name, workflow_id, card, project_id)
        if _should_suppress(session, idem_key, workflow_id):
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

            if "card_type" not in serializable_payload:
                resolved_card_type = payload.get("card_type") if payload else None
                if resolved_card_type is None and card is not None:
                    card_type = getattr(card, "card_type", None)
                    if card_type is None and getattr(card, "card_type_id", None):
                        try:
                            session.refresh(card, ["card_type"])
                            card_type = getattr(card, "card_type", None)
                        except Exception:
                            card_type = None
                    resolved_card_type = getattr(card_type, "name", None) if card_type else None
                if isinstance(resolved_card_type, str):
                    serializable_payload["card_type"] = resolved_card_type
            
            # 创建运行记录
            run = run_manager.create_run(
                workflow_id=workflow_id,
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

                # 调度异步执行
                _async_execute_workflow(run.id)
            else:
                 logger.error(f"[Trigger] Run creation returned no ID for wf {workflow_id}")
                
        except Exception as e:
            logger.exception(f"[Trigger] 创建/触发运行失败: wf={workflow_id}, err={e}")

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

    card_type_name = event.data.get("card_type")
    if card_type_name is None:
        card_type = getattr(card, "card_type", None)
        if card_type is None and getattr(card, "card_type_id", None):
            try:
                session.refresh(card, ["card_type"])
                card_type = getattr(card, "card_type", None)
            except Exception:
                card_type = None
        card_type_name = getattr(card_type, "name", None) if card_type else None
    
    triggers = _match_triggers_for_card(session, "onsave", card, is_created=is_created)
    scope = {
        "card_id": card.id,
        "project_id": card.project_id,
        "card_type": card_type_name,
        "is_created": bool(is_created),
    }
    # 传递 event.data 作为 payload
    run_ids = _execute_triggers(session, "onsave", triggers, scope, card, card.project_id, payload=event.data)
    
    event.data["triggered_run_ids"] = run_ids
    if run_ids:
        logger.info(f"[工作流触发] card.saved - 触发了 {len(run_ids)} 个工作流")


@on_event("project.created")
def handle_project_created(event: Event):
    """处理项目创建事件
    
    如果 template 为 None，则不触发任何工作流（空白项目）。
    """
    from app.services.workflow.trigger_extractor import get_active_triggers_by_event
    
    try:
        session: Session = event.data.get("session")
        project_id: int = event.data.get("project_id")
        template: str | None = event.data.get("template")
        
        if not session or not project_id:
            logger.warning("[工作流触发] project.created 事件缺少必要数据")
            return
        
        # 如果 template 为 None，不触发任何工作流（空白项目）
        if template is None:
            logger.info(f"[工作流触发] project.created - 空白项目，不触发工作流")
            event.data["triggered_run_ids"] = []
            return
        
        # 准备事件数据（用于匹配）
        event_data = {
            "project_id": project_id,
            "template": template,
            "user_id": event.data.get("user_id"),
        }
        
        # 使用新格式匹配
        triggers = get_active_triggers_by_event(session, "project.created", event_data)
        
        scope = {"project_id": project_id, "template": template}
        run_ids = _execute_triggers(session, "project.created", triggers, scope, None, project_id, payload=event.data)
        
        event.data["triggered_run_ids"] = run_ids

        if run_ids:
            logger.info(f"[工作流触发] project.created - 触发了 {len(run_ids)} 个工作流 (template={template})")
    except Exception as e:
        logger.exception(f"[工作流] handle_project_created failed: {e}")

