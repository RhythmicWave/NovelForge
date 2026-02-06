from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select
from datetime import datetime
from loguru import logger

from app.db.session import get_session
from app.db.models import Workflow, WorkflowRun, WorkflowTrigger
from app.schemas.workflow import (
    WorkflowCreate,
    WorkflowUpdate,
    WorkflowRead,
    WorkflowRunRead,
    RunRequest,
    CancelResponse,
    RunStatus,
    NodeTypesResponse,
)
from app.services.workflow import (
    get_node_types,
    get_all_node_metadata,
    get_nodes_by_category,
    RunManager
)


router = APIRouter()


@router.get("/nodes/types", response_model=NodeTypesResponse)
def get_node_types_api():
    """获取所有已注册的工作流节点类型（含完整元数据）
    
    用于前端动态生成节点库和属性面板。
    包含了基于 Pydantic 生成的 JSON Schema。
    """
    all_metadata = get_all_node_metadata()
    
    node_info = []
    for meta in all_metadata:
        # 转换输入/输出端口定义
        inputs = []
        for port in meta.inputs:
            inputs.append({
                "name": port.name,
                "type": port.type,
                "description": port.description,
                "required": port.required
            })
            
        outputs = []
        for port in meta.outputs:
            outputs.append({
                "name": port.name,
                "type": port.type,
                "description": port.description
            })
            
        node_info.append({
            "type": meta.type,
            "category": meta.category,
            "label": meta.label,
            "description": meta.description,
            "inputs": inputs,
            "outputs": outputs,
            "config_schema": meta.config_schema
        })
    
    return {"node_types": node_info}





@router.get("/workflow-node-types/categories")
def get_node_categories():
    """获取节点分类列表"""
    all_metadata = get_all_node_metadata()
    categories = {}
    
    for meta in all_metadata:
        if meta.category not in categories:
            categories[meta.category] = []
        categories[meta.category].append({
            'type': meta.type,
            'label': meta.label,
            'description': meta.description
        })
    
    return {'categories': categories}





@router.get("/workflows", response_model=List[WorkflowRead])
def list_workflows(session: Session = Depends(get_session)):
    return session.exec(select(Workflow)).all()


@router.post("/workflows", response_model=WorkflowRead)
def create_workflow(payload: WorkflowCreate, session: Session = Depends(get_session)):
    wf = Workflow(**payload.model_dump())
    session.add(wf)
    session.commit()
    session.refresh(wf)
    
    # 同步触发器
    _sync_workflow_triggers(session, wf)
    session.commit()
    
    return wf


@router.get("/workflows/{workflow_id}", response_model=WorkflowRead)
def get_workflow(workflow_id: int, session: Session = Depends(get_session)):
    wf = session.get(Workflow, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return wf


@router.put("/workflows/{workflow_id}", response_model=WorkflowRead)
def update_workflow(workflow_id: int, payload: WorkflowUpdate, session: Session = Depends(get_session)):
    """更新工作流（支持版本管理）"""
    wf = session.get(Workflow, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    # 保存当前版本到 previous_version
    if 'definition_json' in payload.model_dump(exclude_unset=True):
        wf.previous_version_json = wf.definition_json
        wf.version += 1
        wf.last_saved_at = datetime.utcnow()
    
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(wf, k, v)
    
    wf.updated_at = datetime.utcnow()
    session.add(wf)
    session.commit()
    session.refresh(wf)
    return wf


@router.post("/workflows/{workflow_id}/rollback", response_model=WorkflowRead)
def rollback_workflow(workflow_id: int, session: Session = Depends(get_session)):
    """回滚到上一版本"""
    wf = session.get(Workflow, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    if not wf.previous_version_json:
        raise HTTPException(status_code=400, detail="没有可回滚的版本")
    
    # 交换当前和上一版本
    current = wf.definition_json
    wf.definition_json = wf.previous_version_json
    wf.previous_version_json = current
    wf.version += 1
    wf.updated_at = datetime.utcnow()
    
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
async def run_workflow(
    workflow_id: int, 
    req: RunRequest, 
    session: Session = Depends(get_session)
):
    """启动工作流运行（异步）"""
    wf = session.get(Workflow, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    # 创建运行管理器
    run_manager = RunManager(session)
    
    # 创建运行
    run = run_manager.create_run(
        workflow_id=workflow_id,
        trigger_data=req.scope_json,
        params=req.params_json,
        idempotency_key=req.idempotency_key
    )
    
    # 异步启动运行
    try:
        await run_manager.start_run(run.id)
    except Exception as e:
        logger.exception(f"启动工作流运行失败: {e}")
        raise HTTPException(status_code=500, detail=f"启动失败: {str(e)}")
    
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
    """验证工作流定义（检查循环依赖、节点类型等）"""
    wf = session.get(Workflow, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    definition = wf.definition_json or {}
    errors: List[str] = []
    warnings: List[str] = []
    
    # 使用新的GraphBuilder验证
    from app.services.workflow.engine import GraphBuilder
    
    try:
        builder = GraphBuilder()
        graph = builder.build(definition)
        
        # 验证节点类型
        allowed_types = set(get_node_types())
        for node_id, node in graph.nodes.items():
            node_type = node.get('type')
            if node_type not in allowed_types:
                errors.append(f"节点 {node_id} 使用了未注册的类型: {node_type}")
        
        # 检查孤立节点
        if len(graph.start_nodes) == 0:
            errors.append("工作流没有起始节点")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "graph_info": {
                "node_count": len(graph.nodes),
                "edge_count": len(graph.edges),
                "start_nodes": graph.start_nodes,
                "topology_order": graph.topology_order
            }
        }
    
    except ValueError as e:
        errors.append(str(e))
        return {
            "valid": False,
            "errors": errors,
            "warnings": warnings
        }
    except Exception as e:
        logger.exception("验证工作流时发生错误")
        errors.append(f"验证失败: {str(e)}")
        return {
            "valid": False,
            "errors": errors,
            "warnings": warnings
        }


@router.post("/workflows/runs/{run_id}/cancel", response_model=CancelResponse)
async def cancel_run(run_id: int, session: Session = Depends(get_session)):
    """取消运行中的工作流"""
    run_manager = RunManager(session)
    ok = await run_manager.cancel_run(run_id)
    return CancelResponse(ok=ok, message="cancelled" if ok else "not running")


@router.get("/workflows/runs/{run_id}/events")
async def stream_events(run_id: int, session: Session = Depends(get_session)):
    """订阅工作流运行事件（SSE）- 支持前端所需的标准事件"""
    import asyncio
    import json
    
    run_manager = RunManager(session)
    
    async def status_stream():
        """定期推送运行状态，直到完成"""
        last_status = None
        seen_nodes = {}  # node_id -> status
        
        try:
            while True:
                # 强制刷新 Session 缓存，确保获取到最新的 DB 状态（特别是 run.status）
                session.expire_all()
                
                # 获取当前状态
                status = run_manager.get_run_status(run_id)
                
                if not status:
                    # 运行不存在
                    yield f"data: {json.dumps({'error': 'Run not found'})}\n\n"
                    break
                
                # 1. 推送默认消息（状态更新）
                yield f"data: {json.dumps(status, ensure_ascii=False)}\n\n"
                
                # 2. 推送节点级事件 (step_started, step_succeeded, step_failed, step_progress)
                current_nodes = {n['node_id']: n for n in status.get('nodes', [])}
                
                for node_id, node_data in current_nodes.items():
                    curr_state = node_data['status']
                    curr_progress = node_data.get('progress', 0)
                    
                    prev_state_info = seen_nodes.get(node_id, {})
                    # 兼容之前只存 string 的情况 (status)
                    if isinstance(prev_state_info, str):
                        prev_state_info = {'status': prev_state_info, 'progress': 0}
                        
                    prev_state = prev_state_info.get('status', 'idle')
                    prev_progress = prev_state_info.get('progress', 0)
                    
                    # 检查状态变化
                    if curr_state != prev_state:
                        seen_nodes[node_id] = {'status': curr_state, 'progress': curr_progress}
                        
                        event_payload = json.dumps({
                            "node_id": node_id,
                            "node_type": node_data['node_type'],
                            "status": curr_state,
                            "error": node_data.get('error')
                        }, ensure_ascii=False)
                        
                        if curr_state == 'running':
                            yield f"event: step_started\ndata: {event_payload}\n\n"
                        elif curr_state == 'success':
                            yield f"event: step_succeeded\ndata: {event_payload}\n\n"
                        elif curr_state == 'error':
                            yield f"event: step_failed\ndata: {event_payload}\n\n"
                            
                    # 检查进度变化 (只在 running 状态下)
                    elif curr_state == 'running' and curr_progress != prev_progress:
                        seen_nodes[node_id]['progress'] = curr_progress
                        
                        progress_payload = json.dumps({
                            "node_id": node_id,
                            "status": curr_state,
                            "progress": curr_progress,
                            "message": f"Progress: {curr_progress}%" # 简单消息，后续可从 logs 获取更详细的
                        }, ensure_ascii=False)
                        yield f"event: step_progress\ndata: {progress_payload}\n\n"

                # 3. 检查是否完成
                run_status = status['status']
                if run_status in ['succeeded', 'failed', 'cancelled']:
                    # 构造 run_completed 事件
                    # 暂时不计算精确的 affected_card_ids，设为空让前端全量刷新
                    # 也可以尝试从 summarry_json 中获取 output
                    completion_payload = {
                        "run_id": run_id,
                        "status": run_status,
                        "utils": {}, 
                        "affected_card_ids": [] # Empty array triggers full refresh in frontend
                    }
                    yield f"event: run_completed\ndata: {json.dumps(completion_payload, ensure_ascii=False)}\n\n"
                    break
                
                # 等待 0.5 秒后再次推送
                await asyncio.sleep(0.5)
                
        except Exception as e:
            logger.exception(f"SSE Error for run {run_id}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(status_stream(), media_type="text/event-stream")


@router.get("/workflows/runs/{run_id}/status", response_model=RunStatus)
def get_run_status(run_id: int, session: Session = Depends(get_session)):
    """获取运行状态（包含节点状态）"""
    run_manager = RunManager(session)
    status = run_manager.get_run_status(run_id)
    
    if not status:
        raise HTTPException(status_code=404, detail="Run not found")
    
    return status


@router.get("/workflows/templates")
def list_templates(session: Session = Depends(get_session)):
    """获取工作流模板列表"""
    stmt = select(Workflow).where(Workflow.is_template == True)
    templates = session.exec(stmt).all()
    return {"templates": templates}


@router.post("/workflows/from-template/{template_id}", response_model=WorkflowRead)
def create_from_template(
    template_id: int,
    name: str,
    session: Session = Depends(get_session)
):
    """从模板创建工作流"""
    template = session.get(Workflow, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    if not template.is_template:
        raise HTTPException(status_code=400, detail="不是模板")
    
    new_workflow = Workflow(
        name=name,
        description=f"基于模板「{template.name}」创建",
        definition_json=template.definition_json,
        dsl_version=template.dsl_version,
        is_template=False
    )
    
    session.add(new_workflow)
    session.commit()
    session.refresh(new_workflow)
    
    # Sync triggers for template-created workflow
    _sync_workflow_triggers(session, new_workflow)
    session.commit() # Trigger sync adds objects but doesn't commit
    
    return new_workflow


def _sync_workflow_triggers(session: Session, wf: Workflow):
    """根据 workflow definition 同步 triggers"""
    if not wf.definition_json:
        return

    # 1. 提取 DSL 中的 trigger 节点
    nodes = wf.definition_json.get("nodes", [])
    new_trigger_specs = []
    
    for node in nodes:
        ntype = node.get("type", "")
        config = node.get("config", {})
        
        if ntype == "Trigger.CardSaved":
            new_trigger_specs.append({
                "trigger_on": "onsave",
                "card_type_name": config.get("card_type"), # 可能是 None (所有类型)
                "filter_json": {"events": config.get("events", ["create", "update"])}, # 存储事件过滤配置
                "is_active": wf.is_active
            })
        elif ntype == "Trigger.Manual":
             new_trigger_specs.append({
                "trigger_on": "manual",
                "card_type_name": None,
                "is_active": wf.is_active
            })
        elif ntype == "Trigger.ProjectCreated":
            new_trigger_specs.append({
                "trigger_on": "onprojectcreate",
                "card_type_name": None,
                "is_active": wf.is_active
            })
    
    # 2. 清理旧触发器 (全量替换策略)
    # 注意：这会重置触发器ID，如果有外部引用需谨慎。目前Trigger表主要是内部查找表。
    stmt = select(WorkflowTrigger).where(WorkflowTrigger.workflow_id == wf.id)
    existing = session.exec(stmt).all()
    for t in existing:
        session.delete(t)
        
    # 3. 创建新触发器
    for spec in new_trigger_specs:
        t = WorkflowTrigger(workflow_id=wf.id, **spec)
        session.add(t)


