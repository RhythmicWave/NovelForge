from typing import List, Optional, Dict, Any
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select
from datetime import datetime
from loguru import logger

from app.db.session import get_session
from app.db.models import Workflow, WorkflowRun
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
from app.schemas.workflow_agent import WorkflowPatchRequest, WorkflowPatchResponse
from app.services.workflow.patcher import (
    compute_code_revision,
    execute_patch_with_validation,
    parse_workflow_code_to_result,
)


def _clean_dollar_prefix(value: Any) -> Any:
    """递归清理值中的 $ 前缀
    
    $ 前缀是后端内部用来标记变量引用的，前端不需要知道。
    在返回给前端时，需要去掉 $ 前缀。
    
    Args:
        value: 任意值（字符串、列表、字典等）
        
    Returns:
        清理后的值
    """
    if isinstance(value, str):
        # 去掉 $ 前缀（变量引用）
        if value.startswith('$'):
            # 处理 ${expression} 格式
            if value.startswith('${') and value.endswith('}'):
                return value[2:-1]  # 去掉 ${ 和 }
            else:
                return value[1:]  # 去掉 $
        return value
    elif isinstance(value, list):
        # 递归处理列表
        return [_clean_dollar_prefix(item) for item in value]
    elif isinstance(value, dict):
        # 递归处理字典
        return {
            _clean_dollar_prefix(k): _clean_dollar_prefix(v)
            for k, v in value.items()
        }
    else:
        # 其他类型保持不变
        return value
from app.services.workflow import (
    get_node_types,
    get_all_node_metadata,
    RunManager
)


router = APIRouter()

# 全局字典：保存运行中的执行器实例（用于暂停/恢复）
_running_executors: Dict[int, Any] = {}  # run_id -> AsyncExecutor


@router.get("/nodes/types", response_model=NodeTypesResponse)
def get_node_types_api():
    """获取所有已注册的工作流节点类型（含完整元数据）
    
    用于前端动态生成节点库和属性面板。
    包含了基于 Pydantic 生成的 JSON Schema。
    """
    all_metadata = get_all_node_metadata()
    
    node_info = []
    for meta in all_metadata:
        node_info.append({
            "type": meta.type,
            "category": meta.category,
            "label": meta.label,
            "description": meta.description,
            "documentation": meta.documentation,  # 添加完整文档
            "input_schema": meta.input_schema,
            "output_schema": meta.output_schema
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


@router.get("/nodes/{node_type}/metadata")
def get_node_metadata_api(node_type: str):
    """获取单个节点的完整元数据

    Args:
        node_type: 节点类型，如 "Novel.Load" 或 "Card.BatchUpsert"

    Returns:
        节点的完整元数据，包括：
        - type: 节点类型
        - category: 分类
        - label: 显示名称
        - description: 描述
        - input_schema: 输入字段的 JSON Schema（从 input_model 生成）
        - output_schema: 输出字段的 JSON Schema（从 output_model 生成）
        - outputs: 输出字段列表（从 output_schema 提取）
    """
    from app.services.workflow.registry import get_node_metadata as get_registry_metadata
    
    # 从注册表获取节点元数据
    registry_meta = get_registry_metadata(node_type)
    if not registry_meta:
        raise HTTPException(status_code=404, detail=f"节点类型不存在: {node_type}")
    
    # 从 output_schema 提取输出字段列表
    outputs = []
    if registry_meta.output_schema and "properties" in registry_meta.output_schema:
        for field_name, field_def in registry_meta.output_schema["properties"].items():
            outputs.append({
                "name": field_name,
                "type": field_def.get("type", "any"),
                "description": field_def.get("description", "")
            })
    
    # 返回元数据
    metadata = {
        "type": registry_meta.type,
        "category": registry_meta.category,
        "label": registry_meta.label,
        "description": registry_meta.description,
        "documentation": registry_meta.documentation,  # 添加完整文档
        "input_schema": registry_meta.input_schema,
        "output_schema": registry_meta.output_schema,
        "outputs": outputs  # 添加输出字段列表
    }
    
    return metadata





@router.get("/workflows", response_model=List[WorkflowRead])
def list_workflows(session: Session = Depends(get_session)):
    return session.exec(select(Workflow)).all()


@router.post("/workflows", response_model=WorkflowRead)
def create_workflow(payload: WorkflowCreate, session: Session = Depends(get_session)):
    wf = Workflow(**payload.model_dump())
    session.add(wf)
    session.commit()
    session.refresh(wf)
    
    # 同步触发器缓存（优化性能）
    from app.services.workflow.trigger_extractor import sync_triggers_cache
    sync_triggers_cache(wf, session)
    
    session.commit()
    
    return wf


@router.get("/workflows/project-templates")
def get_project_templates(session: Session = Depends(get_session)):
    """获取项目创建模板列表
    
    返回所有包含 Trigger.ProjectCreated 触发器的工作流，
    以及它们的模板标识（template 参数）。
    
    前端可以根据这些信息渲染项目创建对话框的模板选择下拉框。
    """
    # 查询所有激活的工作流
    stmt = select(Workflow).where(Workflow.is_active == True)
    workflows = session.exec(stmt).all()
    
    templates = []
    
    for wf in workflows:
        if not wf.triggers_cache:
            continue
        
        # 查找项目创建触发器
        for trigger in wf.triggers_cache:
            if trigger.get("event") == "project.created":
                # 提取 template 参数
                match = trigger.get("match") or {}
                template_id = match.get("template")
                
                templates.append({
                    "workflow_id": wf.id,
                    "workflow_name": wf.name,
                    "template": template_id,  # 模板标识（如 "snowflake"）
                    "description": wf.description
                })
    
    logger.info(f"[API] 找到 {len(templates)} 个项目创建模板")
    return {"templates": templates}


@router.get("/workflows/{workflow_id}", response_model=WorkflowRead)
def get_workflow(workflow_id: int, session: Session = Depends(get_session)):
    wf = session.get(Workflow, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return wf


@router.put("/workflows/{workflow_id}", response_model=WorkflowRead)
def update_workflow(workflow_id: int, payload: WorkflowUpdate, session: Session = Depends(get_session)):
    """更新工作流"""
    wf = session.get(Workflow, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(wf, k, v)
    
    wf.updated_at = datetime.utcnow()
    session.add(wf)
    session.commit()
    session.refresh(wf)
    
    # 同步触发器缓存（新方式 - 优化性能）
    from app.services.workflow.trigger_extractor import sync_triggers_cache
    sync_triggers_cache(wf, session)
    session.commit()
    
    return wf


@router.delete("/workflows/{workflow_id}")
def delete_workflow(workflow_id: int, session: Session = Depends(get_session)):
    wf = session.get(Workflow, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    session.delete(wf)
    session.commit()
    return {"ok": True}


@router.get("/workflows/runs/{run_id}", response_model=WorkflowRunRead)
def get_run(run_id: int, session: Session = Depends(get_session)):
    run = session.get(WorkflowRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/workflows/{workflow_id}/runs", response_model=List[WorkflowRunRead])
def list_workflow_runs(
    workflow_id: int,
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    session: Session = Depends(get_session)
):
    """获取指定工作流的运行列表
    
    Args:
        workflow_id: 工作流 ID
        limit: 返回数量限制（默认 50）
        offset: 偏移量（默认 0）
        status: 过滤状态（可选）：running, paused, succeeded, failed, cancelled
    
    Returns:
        运行列表，按创建时间倒序
    """
    from sqlmodel import select, desc
    
    stmt = select(WorkflowRun).where(
        WorkflowRun.workflow_id == workflow_id
    )
    
    # 添加状态筛选
    if status:
        stmt = stmt.where(WorkflowRun.status == status)
    
    stmt = stmt.order_by(
        desc(WorkflowRun.created_at)
    ).limit(limit).offset(offset)
    
    runs = session.exec(stmt).all()
    return runs


@router.get("/runs", response_model=List[WorkflowRunRead])
def list_all_runs(
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    session: Session = Depends(get_session)
):
    """获取所有工作流的运行列表
    
    Args:
        limit: 返回数量限制（默认 50）
        offset: 偏移量（默认 0）
        status: 过滤状态（可选）：running, paused, succeeded, failed, cancelled
    
    Returns:
        运行列表，按创建时间倒序
    """
    from sqlmodel import select, desc
    import logging
    logger = logging.getLogger(__name__)
    
    stmt = select(WorkflowRun).order_by(desc(WorkflowRun.created_at))
    
    if status:
        stmt = stmt.where(WorkflowRun.status == status)
    
    stmt = stmt.limit(limit).offset(offset)
    
    runs = session.exec(stmt).all()
    
    # 调试：打印第一个运行的时间
    if runs:
        logger.info(f"[list_all_runs] 第一个运行: id={runs[0].id}, created_at={runs[0].created_at}, type={type(runs[0].created_at)}")
    
    return runs


@router.post("/workflows/{workflow_id}/validate")
def validate_workflow_endpoint(workflow_id: int, session: Session = Depends(get_session)):
    """验证工作流定义（完整静态检查）
    
    检查内容：
    - 语法错误
    - 节点类型错误
    - 字段访问错误
    - 表达式语法错误
    - 类型不匹配
    - Expression 节点特殊规则
    """
    from app.services.workflow.validator import validate_workflow
    
    wf = session.get(Workflow, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    code = wf.definition_code or ""
    
    if not code:
        return {
            "is_valid": False,
            "errors": [{
                "line": 0,
                "variable": "",
                "error_type": "syntax",
                "message": "工作流缺少代码内容",
                "suggestion": None
            }],
            "warnings": []
        }
    
    # 执行完整校验
    result = validate_workflow(code, session=session)
    
    return result.to_dict()


@router.post("/workflows/runs/{run_id}/cancel", response_model=CancelResponse)
async def cancel_run(run_id: int, session: Session = Depends(get_session)):
    """取消运行中的工作流"""
    run_manager = RunManager(session)
    ok = await run_manager.cancel_run(run_id)
    return CancelResponse(ok=ok, message="cancelled" if ok else "not running")


@router.post("/workflows/runs/{run_id}/pause")
async def pause_run(run_id: int, session: Session = Depends(get_session)):
    """暂停运行中的工作流
    
    立即取消所有异步任务并更新数据库状态。
    """
    logger.info(f"[API] 收到暂停请求: run_id={run_id}")
    
    # 获取运行记录
    run = session.get(WorkflowRun, run_id)
    if not run:
        logger.warning(f"[API] 运行不存在: run_id={run_id}")
        raise HTTPException(status_code=404, detail="Run not found")
    
    # 检查状态
    if run.status not in ["running", "queued"]:
        logger.warning(f"[API] 运行状态不是 running 或 queued: run_id={run_id}, status={run.status}")
        raise HTTPException(status_code=400, detail=f"无法暂停状态为 {run.status} 的运行")
    
    # 如果执行器存在，调用其 pause() 方法
    executor = _running_executors.get(run_id)
    if executor:
        logger.info(f"[API] 调用执行器的 pause() 方法: run_id={run_id}")
        executor.pause()  # 同步调用，立即返回
    else:
        logger.warning(f"[API] 执行器不存在（可能已完成或未启动）: run_id={run_id}")
    
    # 更新状态为暂停
    run.status = "paused"
    session.add(run)
    session.commit()
    
    logger.info(f"[API] 暂停成功: run_id={run_id}")
    return {"ok": True, "message": "paused"}


@router.post("/workflows/runs/{run_id}/resume")
async def resume_run(run_id: int, session: Session = Depends(get_session)):
    """恢复暂停的工作流
    
    如果服务器重启，会重新启动运行并自动恢复状态。
    """
    run_manager = RunManager(session)
    ok = await run_manager.resume_run(run_id)
    if not ok:
        raise HTTPException(status_code=400, detail="无法恢复运行（运行不存在或状态不是暂停）")
    return {"ok": True, "message": "resumed"}


@router.get("/workflows/{workflow_id}/execute-stream")
async def execute_code_workflow_stream(
    workflow_id: int,
    resume: bool = False,
    run_id: Optional[int] = None,
    session: Session = Depends(get_session)
):
    """执行代码式工作流（流式SSE推送）

    实时推送执行事件，同时创建 run 记录并保存状态（支持暂停/恢复）。
    
    Args:
        workflow_id: 工作流 ID
        resume: 是否恢复执行（默认 False，从头开始）
        run_id: 恢复执行时的 run ID（resume=True 时必须提供）
    """
    import json
    from app.services.workflow.parser.marker_parser import WorkflowParser
    from app.services.workflow.engine.async_executor import AsyncExecutor
    from app.services.workflow.engine.state_manager import StateManager
    from app.services.workflow.registry import NodeRegistry

    # 获取工作流
    workflow = session.get(Workflow, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    if not workflow.is_active:
        raise HTTPException(status_code=400, detail="Workflow is not active")

    code = workflow.definition_code or ""
    if not code:
        raise HTTPException(status_code=400, detail="Workflow code is empty")

    # 处理 run 记录
    run_manager = RunManager(session)
    
    if resume:
        # 恢复执行：必须提供 run_id
        if not run_id:
            raise HTTPException(status_code=400, detail="resume=True 时必须提供 run_id")
        
        run = session.get(WorkflowRun, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        
        if run.workflow_id != workflow_id:
            raise HTTPException(status_code=400, detail="Run 不属于该工作流")
        
        # 更新状态为运行中
        run.status = "running"
        session.add(run)
        session.commit()
        
        logger.info(f"[CodeWorkflow] 恢复运行: run_id={run_id}, workflow_id={workflow_id}")
    else:
        # 新建执行：使用 RunManager 创建（带幂等性保护）
        # 生成幂等键：基于工作流ID和时间窗口（5秒）
        from datetime import datetime
        time_window = int(datetime.utcnow().timestamp() / 5)  # 5秒时间窗口
        idempotency_key = f"manual_exec:{workflow_id}:{time_window}"
        
        run = run_manager.create_run(
            workflow_id=workflow_id,
            idempotency_key=idempotency_key
        )
        run_id = run.id
        
        # 如果是复用的运行记录，检查状态
        if run.status == "running":
            logger.warning(f"[CodeWorkflow] 复用现有运行记录（幂等性保护）: run_id={run_id}, workflow_id={workflow_id}")
        else:
            # 更新状态为运行中
            run.status = "running"
            session.add(run)
            session.commit()
            logger.info(f"[CodeWorkflow] 创建运行记录: run_id={run_id}, workflow_id={workflow_id}")

    async def event_stream():
        """流式推送执行事件"""
        executor = None
        try:
            # 解析代码
            from app.services.workflow.parser.marker_parser import WorkflowParser
            parser = WorkflowParser()
            plan = parser.parse(code)

            logger.info(f"[CodeWorkflow] 开始流式执行: run_id={run_id}, 语句数={len(plan.statements)}, resume={resume}")

            # 创建状态管理器和执行器
            state_manager = StateManager(session)
            
            # 如果不是恢复执行，清理旧状态
            if not resume:
                from app.services.workflow.engine.execution_state import ExecutionState
                exec_state = ExecutionState(run_id)
                exec_state.clear_node_states(session)
            
            executor = AsyncExecutor(
                session=session,
                state_manager=state_manager,
                run_id=run_id
            )
            
            # ⚠️ 关键：如果已有执行器在运行，先取消它
            if run_id in _running_executors:
                old_executor = _running_executors[run_id]
                logger.warning(f"[CodeWorkflow] 发现旧执行器仍在运行，先取消: run_id={run_id}")
                try:
                    old_executor.pause()  # 同步调用，立即返回
                except Exception as e:
                    logger.error(f"[CodeWorkflow] 取消旧执行器失败: {e}")
            
            # 保存执行器引用（用于暂停）
            _running_executors[run_id] = executor
            logger.info(f"[CodeWorkflow] 执行器已注册: run_id={run_id}")

            # 推送 run_id（让前端知道当前运行的 ID）
            yield f"data: {json.dumps({'type': 'run_started', 'run_id': run_id}, ensure_ascii=False)}\n\n"

            # 流式执行
            async for event in executor.execute_stream(plan, initial_context={}):
                # 检查是否已暂停（优先检查）
                if executor.is_paused:
                    logger.info(f"[CodeWorkflow] 检测到暂停状态，停止执行: run_id={run_id}")
                    # 推送暂停事件
                    yield f"data: {json.dumps({'type': 'paused', 'message': '工作流已暂停'}, ensure_ascii=False)}\n\n"
                    return  # 停止生成器
                
                # 构造SSE事件
                event_data = {
                    "type": event.type,
                    "statement": {
                        "variable": event.statement.variable,
                        "code": event.statement.code or f"{event.statement.variable} = {event.statement.node_type or 'expression'}(...)",
                        "line": event.statement.line_number,
                        "description": getattr(event.statement, 'description', '') or "",
                    }
                }

                if event.type == "start":
                    event_data["message"] = event.message or f"开始执行: {event.statement.variable}"
                elif event.type == "progress":
                    event_data["percent"] = event.percent
                    event_data["message"] = event.message
                elif event.type == "complete":
                    event_data["result"] = event.result
                    # 检查是否是恢复的节点
                    if event.message and "[已恢复]" in event.message:
                        event_data["resumed"] = True
                elif event.type == "error":
                    event_data["error"] = event.error

                # 推送事件
                try:
                    yield f"data: {json.dumps(event_data, ensure_ascii=False, default=str)}\n\n"
                except Exception as e:
                    # 如果推送失败（客户端断开），停止执行
                    logger.warning(f"[CodeWorkflow] 推送事件失败（客户端可能断开）: {e}")
                    executor.pause()  # 标记为暂停
                    return

            # 更新 run 状态为成功
            state_manager.update_run_status(run_id, "succeeded")

            # 推送完成事件
            yield f"data: {json.dumps({'type': 'end', 'message': '工作流执行完成'}, ensure_ascii=False)}\n\n"

            logger.info(f"[CodeWorkflow] 流式执行完成: run_id={run_id}")

        except asyncio.CancelledError:
            # 客户端断开连接（暂停）
            logger.info(f"[CodeWorkflow] 客户端断开连接，暂停执行: run_id={run_id}")
            try:
                state_manager = StateManager(session)
                state_manager.update_run_status(run_id, "paused")
            except:
                pass
            raise  # 重新抛出以正确关闭连接
            
        except Exception as e:
            logger.exception(f"[CodeWorkflow] 流式执行失败: run_id={run_id}")
            
            # 更新 run 状态为失败
            try:
                state_manager = StateManager(session)
                state_manager.update_run_status(run_id, "failed")
            except:
                pass
            
            error_data = {
                "type": "error",
                "error": str(e),
                "message": "工作流执行失败"
            }
            yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
        
        finally:
            # 清理执行器引用
            if run_id in _running_executors:
                del _running_executors[run_id]
                logger.info(f"[CodeWorkflow] 执行器已清理: run_id={run_id}")

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.delete("/workflows/runs/{run_id}")
def delete_run(run_id: int, session: Session = Depends(get_session)):
    """删除运行记录
    
    删除指定的运行记录及其相关的节点状态。
    """
    # 获取运行记录
    run = session.get(WorkflowRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    # 检查状态：不允许删除正在运行的记录
    if run.status == "running":
        raise HTTPException(status_code=400, detail="无法删除正在运行的记录，请先暂停或取消")
    
    # 删除相关的节点状态
    from app.db.models import NodeExecutionState
    stmt = select(NodeExecutionState).where(NodeExecutionState.run_id == run_id)
    node_states = session.exec(stmt).all()
    for node_state in node_states:
        session.delete(node_state)
    
    # 删除运行记录
    session.delete(run)
    session.commit()
    
    logger.info(f"[API] 运行记录已删除: run_id={run_id}")
    return {"ok": True, "message": "deleted"}


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
        definition_code=template.definition_code,
        dsl_version=template.dsl_version,
        is_template=False
    )
    
    session.add(new_workflow)
    session.commit()
    session.refresh(new_workflow)
    
    # 同步触发器缓存
    from app.services.workflow.trigger_extractor import sync_triggers_cache
    sync_triggers_cache(new_workflow, session)
    session.commit()
    
    return new_workflow


# ============================================================
# 代码式工作流 API
# ============================================================

@router.post("/workflows/parse")
def parse_workflow_code(payload: Dict[str, Any]):
    """解析工作流代码（验证语法）
    
    Args:
        payload: 包含 code 字段的字典（注释标记 DSL）
        
    Returns:
        解析结果
    """
    code = payload.get("code", "")
    if not code:
        return {"success": False, "errors": ["代码不能为空"]}

    parsed = parse_workflow_code_to_result(code)
    if not parsed.get("ok"):
        error = str(parsed.get("error") or "parse_failed")
        logger.error(f"代码解析失败: {error}")
        return {
            "success": False,
            "errors": [error],
        }

    statements = []
    for stmt in parsed.get("statements", []):
        variable = stmt.get("variable")
        cleaned_config = _clean_dollar_prefix(stmt.get("config"))
        statements.append({
            "variable": variable,
            "code": stmt.get("code") or (f"{variable} = ..." if variable else "..."),
            "line": stmt.get("line"),
            "node_type": stmt.get("node_type"),
            "config": cleaned_config,
            "is_async": bool(stmt.get("is_async")),
            "disabled": bool(stmt.get("disabled")),
            "description": stmt.get("description", "") or "",
        })

    return {
        "success": True,
        "statements": statements,
    }


@router.post("/workflows/rename-variable")
def rename_variable(payload: Dict[str, Any]):
    """重命名变量并更新所有引用
    
    Args:
        payload: 包含 code, old_name, new_name 的字典
        
    Returns:
        重命名结果
    """
    from app.services.workflow.parser.marker_renamer import rename_variable as marker_rename
    
    code = payload.get("code", "")
    old_name = payload.get("old_name", "")
    new_name = payload.get("new_name", "")
    
    logger.info(f"[重命名] 开始重命名变量: {old_name} -> {new_name}")
    
    if not code or not old_name or not new_name:
        return {"success": False, "error": "缺少必要参数"}
    
    try:
        # 使用注释标记 DSL 重命名器
        new_code = marker_rename(code, old_name, new_name)
        
        logger.info(f"[重命名] 新代码:\n{new_code}")
        
        return {
            "success": True,
            "new_code": new_code
        }
    except Exception as e:
        logger.error(f"变量重命名失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": str(e)
        }


@router.post("/workflows/code", response_model=WorkflowRead)
def save_code_workflow(payload: Dict[str, Any], session: Session = Depends(get_session)):
    """保存代码式工作流"""
    name = payload.get("name")
    code = payload.get("code")

    if not name or not code:
        raise HTTPException(status_code=400, detail="name和code不能为空")

    # 创建工作流，将代码存储在 definition_code 字段
    wf = Workflow(
        name=name,
        description="代码式工作流",
        definition_code=code,
        dsl_version=2
    )

    session.add(wf)
    session.commit()
    session.refresh(wf)
    
    # 同步触发器缓存
    from app.services.workflow.trigger_extractor import sync_triggers_cache
    sync_triggers_cache(wf, session)
    session.commit()

    return wf


@router.get("/workflows/{workflow_id}/code")
def get_code_workflow(workflow_id: int, session: Session = Depends(get_session)):
    """获取代码式工作流"""
    wf = session.get(Workflow, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    # 代码式工作流使用 definition_code 字段
    return {
        "id": wf.id,
        "name": wf.name,
        "code": wf.definition_code or "",
        "revision": compute_code_revision(wf.definition_code or ""),
        "keep_run_history": wf.keep_run_history or False
    }


@router.post("/workflows/{workflow_id}/patch", response_model=WorkflowPatchResponse)
def patch_workflow_code(
    workflow_id: int,
    payload: WorkflowPatchRequest,
    session: Session = Depends(get_session),
):
    wf = session.get(Workflow, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    old_code = wf.definition_code or ""
    current_revision = compute_code_revision(old_code)
    if payload.base_revision != current_revision:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "revision_mismatch",
                "message": "代码已更新，请刷新后重试",
                "current_revision": current_revision,
            },
        )

    try:
        execution = execute_patch_with_validation(old_code, payload.patch_ops, session=session)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    new_code = execution.new_code
    changed_nodes = execution.changed_nodes
    applied_ops = execution.applied_ops
    parse_result = execution.parse_result
    validation = execution.validation
    diff = execution.diff

    if payload.dry_run:
        return WorkflowPatchResponse(
            success=bool(parse_result.get("ok")) and bool(validation.get("is_valid")),
            workflow_id=workflow_id,
            base_revision=current_revision,
            new_revision=compute_code_revision(new_code),
            applied_ops=applied_ops,
            changed_nodes=changed_nodes,
            diff=diff,
            new_code=new_code,
            parse_result=parse_result,
            validation=validation,
            error=parse_result.get("error") if not parse_result.get("ok") else None,
        )

    if not parse_result.get("ok"):
        return WorkflowPatchResponse(
            success=False,
            workflow_id=workflow_id,
            base_revision=current_revision,
            applied_ops=applied_ops,
            changed_nodes=changed_nodes,
            diff=diff,
            new_code=new_code,
            parse_result=parse_result,
            validation=validation,
            error=str(parse_result.get("error") or "parse_failed"),
        )

    if not validation.get("is_valid"):
        return WorkflowPatchResponse(
            success=False,
            workflow_id=workflow_id,
            base_revision=current_revision,
            applied_ops=applied_ops,
            changed_nodes=changed_nodes,
            diff=diff,
            new_code=new_code,
            parse_result=parse_result,
            validation=validation,
            error="validate_failed",
        )

    wf.definition_code = new_code
    wf.updated_at = datetime.utcnow()
    session.add(wf)
    session.commit()
    session.refresh(wf)

    from app.services.workflow.trigger_extractor import sync_triggers_cache

    sync_triggers_cache(wf, session)
    session.commit()

    return WorkflowPatchResponse(
        success=True,
        workflow_id=workflow_id,
        base_revision=current_revision,
        new_revision=compute_code_revision(wf.definition_code or ""),
        applied_ops=applied_ops,
        changed_nodes=changed_nodes,
        diff=diff,
        new_code=wf.definition_code or "",
        parse_result=parse_result,
        validation=validation,
    )
