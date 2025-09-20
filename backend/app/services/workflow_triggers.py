from typing import List
from sqlmodel import Session, select

from app.db.models import WorkflowTrigger, Card, Workflow
from app.services.workflow_engine import engine as wf_engine


def _match_triggers_for_card(session: Session, event: str, card: Card) -> List[WorkflowTrigger]:
    q = select(WorkflowTrigger).where(
        WorkflowTrigger.trigger_on == event,
        WorkflowTrigger.is_active == True,  # noqa: E712
    )
    triggers = session.exec(q).all()
    matched: List[WorkflowTrigger] = []
    for t in triggers:
        # 过滤 card_type
        if t.card_type_name and card.card_type and card.card_type.name != t.card_type_name:
            continue
        # filter_json 预留：当前不实现复杂匹配
        matched.append(t)
    return matched


def trigger_on_card_save(session: Session, card: Card) -> List[int]:
    """保存/更新卡片后触发 OnSave 类型工作流，返回 run_id 列表。"""
    run_ids: List[int] = []
    triggers = _match_triggers_for_card(session, "onsave", card)
    for t in triggers:
        wf = session.get(Workflow, t.workflow_id)
        if not wf or not wf.is_active:
            continue
        run = wf_engine.create_run(
            session=session,
            workflow=wf,
            scope_json={"card_id": card.id, "project_id": card.project_id},
            params_json={},
            idempotency_key=None,
        )
        wf_engine.run(session, run)
        if run.id:
            run_ids.append(int(run.id))
    return run_ids


def trigger_on_generate_finish(session: Session, card: Card | None, project_id: int | None) -> List[int]:
    """生成/续写完成后触发 OnGenerateFinish 类型工作流，返回 run_id 列表。"""
    run_ids: List[int] = []
    q = select(WorkflowTrigger).where(
        WorkflowTrigger.trigger_on == "ongenfinish",
        WorkflowTrigger.is_active == True,  # noqa: E712
    )
    triggers = session.exec(q).all()
    for t in triggers:
        if card and t.card_type_name and card.card_type and card.card_type.name != t.card_type_name:
            continue
        wf = session.get(Workflow, t.workflow_id)
        if not wf or not wf.is_active:
            continue
        scope = {"project_id": project_id}
        if card and card.id:
            scope["card_id"] = card.id
        run = wf_engine.create_run(session, wf, scope_json=scope, params_json={}, idempotency_key=None)
        wf_engine.run(session, run)
        if run.id:
            run_ids.append(int(run.id))
    return run_ids


