from typing import List
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from app.db.session import get_session
from app.db.models import Workflow, WorkflowRun, WorkflowTrigger
from app.schemas.workflow import (
    WorkflowCreate,
    WorkflowUpdate,
    WorkflowRead,
    WorkflowRunRead,
    RunRequest,
    CancelResponse,
    WorkflowTriggerCreate,
    WorkflowTriggerUpdate,
    WorkflowTriggerRead,
)
from app.services.workflow_engine import engine as wf_engine


router = APIRouter()


@router.get("/workflows", response_model=List[WorkflowRead])
def list_workflows(session: Session = Depends(get_session)):
    return session.exec(select(Workflow)).all()


@router.get("/workflow-triggers", response_model=List[WorkflowTriggerRead])
def list_triggers(session: Session = Depends(get_session)):
    """返回所有工作流触发器列表（独立资源路径，避免与 /workflows/{workflow_id} 冲突）。"""
    items = session.exec(select(WorkflowTrigger)).all()
    return items

@router.post("/workflow-triggers", response_model=WorkflowTriggerRead)
def create_trigger(payload: WorkflowTriggerCreate, session: Session = Depends(get_session)):
    t = WorkflowTrigger(**payload.model_dump())
    session.add(t)
    session.commit()
    session.refresh(t)
    return t

@router.put("/workflow-triggers/{trigger_id}", response_model=WorkflowTriggerRead)
def update_trigger(trigger_id: int, payload: WorkflowTriggerUpdate, session: Session = Depends(get_session)):
    t = session.get(WorkflowTrigger, trigger_id)
    if not t:
        raise HTTPException(status_code=404, detail="Trigger not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(t, k, v)
    session.add(t)
    session.commit()
    session.refresh(t)
    return t

@router.delete("/workflow-triggers/{trigger_id}")
def delete_trigger(trigger_id: int, session: Session = Depends(get_session)):
    t = session.get(WorkflowTrigger, trigger_id)
    if not t:
        raise HTTPException(status_code=404, detail="Trigger not found")
    session.delete(t)
    session.commit()
    return {"ok": True}


@router.post("/workflows", response_model=WorkflowRead)
def create_workflow(payload: WorkflowCreate, session: Session = Depends(get_session)):
    wf = Workflow(**payload.model_dump())
    session.add(wf)
    session.commit()
    session.refresh(wf)
    return wf


@router.get("/workflows/{workflow_id}", response_model=WorkflowRead)
def get_workflow(workflow_id: int, session: Session = Depends(get_session)):
    wf = session.get(Workflow, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return wf


@router.put("/workflows/{workflow_id}", response_model=WorkflowRead)
def update_workflow(workflow_id: int, payload: WorkflowUpdate, session: Session = Depends(get_session)):
    wf = session.get(Workflow, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(wf, k, v)
    session.add(wf)
    session.commit()
    session.refresh(wf)
    return wf


@router.delete("/workflows/{workflow_id}")
def delete_workflow(workflow_id: int, session: Session = Depends(get_session)):
    wf = session.get(Workflow, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    session.delete(wf)
    session.commit()
    return {"ok": True}


@router.post("/workflows/{workflow_id}/run", response_model=WorkflowRunRead)
def run_workflow(workflow_id: int, req: RunRequest, session: Session = Depends(get_session)):
    wf = session.get(Workflow, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    run = wf_engine.create_run(session, wf, req.scope_json, req.params_json, req.idempotency_key)
    wf_engine.run(session, run)
    session.refresh(run)
    return run


@router.get("/workflows/runs/{run_id}", response_model=WorkflowRunRead)
def get_run(run_id: int, session: Session = Depends(get_session)):
    run = session.get(WorkflowRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.post("/workflows/{workflow_id}/validate")
def validate_workflow(workflow_id: int, session: Session = Depends(get_session)):
    wf = session.get(Workflow, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    dsl = wf.definition_json or {}
    nodes = list(dsl.get("nodes") or [])
    canonical = wf_engine._canonicalize(nodes)  # type: ignore[attr-defined]
    # 简单校验：ForEach/Range 必须有 body
    errors: List[str] = []
    for i, n in enumerate(canonical):
        t = n.get("type")
        if t in ("List.ForEach", "List.ForEachRange") and not n.get("body"):
            errors.append(f"Node#{i}({t}) 缺少 body")
    return {"canonical_nodes": canonical, "errors": errors}


@router.post("/workflows/runs/{run_id}/cancel", response_model=CancelResponse)
def cancel_run(run_id: int):
    ok = wf_engine.cancel(run_id)
    return CancelResponse(ok=ok, message="cancelled" if ok else "not running")


@router.get("/workflows/runs/{run_id}/events")
async def stream_events(run_id: int):
    async def event_publisher():
        async for evt in wf_engine.subscribe_events(run_id):
            yield evt

    return StreamingResponse(event_publisher(), media_type="text/event-stream")


