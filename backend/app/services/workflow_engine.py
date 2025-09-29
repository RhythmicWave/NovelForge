import asyncio
from typing import AsyncIterator, Dict, Optional, Any, List, Callable
from datetime import datetime
from sqlmodel import Session, select

from app.db.models import Workflow, WorkflowRun
from app.services import nodes as builtin_nodes
from loguru import logger


class LocalAsyncEngine:
    """
    极简本地执行器（MVP）
    - 线性执行 nodes；支持 List.ForEach/List.ForEachRange（body 必须存在）
    - 事件：step_started/step_succeeded/step_failed/run_completed
    - 规范化：执行前对 DSL 做兼容重写（ForEach 无 body → 将紧随节点折叠为 body）
    """

    def __init__(self) -> None:
        self._run_tasks: Dict[int, asyncio.Task] = {}
        self._event_queues: Dict[int, "asyncio.Queue[str]"] = {}

    # ---------------- background & events ----------------
    async def _publish(self, run_id: int, event: str) -> None:
        # 兜底：若队列不存在则先创建，避免前端晚订阅时丢事件
        queue = self._event_queues.get(run_id)
        if queue is None:
            logger.info(f"[工作流] _publish 发现队列不存在，已兜底创建 run_id={run_id}")
            queue = asyncio.Queue()
            self._event_queues[run_id] = queue
        await queue.put(event)

    async def _close_queue(self, run_id: int) -> None:
        queue = self._event_queues.get(run_id)
        if queue is not None:
            await queue.put("__CLOSE__")

    def _ensure_queue(self, run_id: int) -> asyncio.Queue:
        q = self._event_queues.get(run_id)
        if q is None:
            q = asyncio.Queue()
            self._event_queues[run_id] = q
            logger.info(f"[工作流] 已创建事件队列 run_id={run_id}")
        return q

    def subscribe_events(self, run_id: int) -> AsyncIterator[str]:
        queue = self._ensure_queue(run_id)

        async def _gen() -> AsyncIterator[str]:
            while True:
                item = await queue.get()
                if item == "__CLOSE__":
                    break
                yield item
        return _gen()

    def _background_run(self, coro_factory: Callable[[], asyncio.Future], run_id: int) -> Optional[asyncio.Task]:
        try:
            loop = asyncio.get_running_loop()
            return loop.create_task(coro_factory())
        except RuntimeError:
            try:
                import anyio  # type: ignore
                logger.info(f"[工作流] 无事件循环；通过 anyio.from_thread.run 投递 run_id={run_id}")
                return anyio.from_thread.run(asyncio.create_task, coro_factory())
            except Exception:
                logger.warning(f"[工作流] anyio 失败；同步执行 run_id={run_id}")
                asyncio.run(coro_factory())
                return None

    # ---------------- create run ----------------
    def create_run(self, session: Session, workflow: Workflow, scope_json: Optional[dict], params_json: Optional[dict], idempotency_key: Optional[str]) -> WorkflowRun:
        run = WorkflowRun(
            workflow_id=workflow.id,
            definition_version=workflow.version,
            status="queued",
            scope_json=scope_json,
            params_json=params_json,
            idempotency_key=idempotency_key,
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        # 提前创建事件队列，确保即便前端稍后订阅也不会丢第一批事件
        self._ensure_queue(run.id)
        logger.info(f"[工作流] Run 已创建并初始化事件队列 run_id={run.id} workflow_id={workflow.id}")
        return run

    # ---------------- nodes ----------------
    def _resolve_node_fn(self, type_name: str):
        mapping = {
            # Card 类节点
            "Card.Read": builtin_nodes.node_card_read,
            "Card.ModifyContent": builtin_nodes.node_card_modify_content,
            "Card.UpsertChildByTitle": builtin_nodes.node_card_upsert_child_by_title,
            "Card.ClearFields": builtin_nodes.node_card_clear_fields,
        }
        fn = mapping.get(type_name)
        if not fn:
            raise ValueError(f"未知节点类型: {type_name}")
        return fn

    # ---------------- canonicalize ----------------
    @staticmethod
    def _canonicalize(nodes: List[dict]) -> List[dict]:
        """将 DSL 规范化：
        - ForEach/ForEachRange 若无 body，则将后一个节点折叠为其 body，并跳过单独执行。
        """
        out: List[dict] = []
        i = 0
        while i < len(nodes):
            n = nodes[i]
            ntype = n.get("type")
            if ntype in ("List.ForEach", "List.ForEachRange") and not n.get("body") and i + 1 < len(nodes):
                compat = dict(n)
                compat["body"] = [nodes[i + 1]]
                out.append(compat)
                logger.warning("[工作流] 兼容重写：ForEach/Range 缺少 body，已将后一节点折叠为 body")
                i += 2
                continue
            out.append(n)
            i += 1
        return out

    # ---------------- execute ----------------
    async def _execute_dsl(self, session: Session, workflow: Workflow, run: WorkflowRun) -> None:
        dsl: Dict[str, Any] = workflow.definition_json or {}
        raw_nodes: List[dict] = list(dsl.get("nodes") or [])
        
        # 检查是否是标准格式（包含edges）
        is_standard_format = "edges" in dsl and isinstance(dsl["edges"], list)
        
        if is_standard_format:
            # 标准格式：基于edges执行
            await self._execute_standard_format(session, workflow, run, dsl)
        else:
            # 旧格式：保持原有逻辑
            await self._execute_legacy_format(session, workflow, run, raw_nodes)

    async def _execute_standard_format(self, session: Session, workflow: Workflow, run: WorkflowRun, dsl: dict) -> None:
        """执行标准格式的工作流（基于nodes+edges）"""
        nodes: List[dict] = list(dsl.get("nodes") or [])
        edges: List[dict] = list(dsl.get("edges") or [])
        state: Dict[str, Any] = {"scope": run.scope_json or {}, "touched_card_ids": set()}
        
        logger.info(f"[工作流] 开始执行标准格式 run_id={run.id} workflow_id={workflow.id} nodes={len(nodes)} edges={len(edges)}")
        
        # 构建节点映射和依赖图
        node_map = {n["id"]: n for n in nodes}
        dependencies = {}  # node_id -> [predecessor_ids]
        successors = {}    # node_id -> [successor_ids]
        
        for edge in edges:
            source, target = edge["source"], edge["target"]
            if target not in dependencies:
                dependencies[target] = []
            if source not in successors:
                successors[source] = []
            dependencies[target].append(source)
            successors[source].append(target)
        
        # 找到起始节点（没有依赖的节点）
        start_nodes = [n["id"] for n in nodes if n["id"] not in dependencies]
        if not start_nodes:
            logger.warning("[工作流] 没有找到起始节点，选择第一个节点")
            start_nodes = [nodes[0]["id"]] if nodes else []
        
        executed = set()
        
        async def execute_node(node_id: str):
            if node_id in executed or node_id not in node_map:
                return
            
            node = node_map[node_id]
            ntype = node.get("type")
            params = node.get("params") or {}
            
            logger.info(f"[工作流] 标准格式节点开始 id={node_id} type={ntype}")
            await self._publish(run.id, f"event: step_started\ndata: {ntype}\n\n")
            
            try:
                # 对于ForEach类型，需要特殊处理
                if ntype in ("List.ForEach", "List.ForEachRange"):
                    # 获取后续节点作为body
                    body_node_ids = successors.get(node_id, [])
                    body_nodes = [node_map[bid] for bid in body_node_ids if bid in node_map]
                    
                    if ntype == "List.ForEach":
                        builtin_nodes.node_list_foreach(session, state, params, 
                            lambda: self._execute_body_nodes(body_nodes, session, state, run.id))
                    else:  # List.ForEachRange
                        builtin_nodes.node_list_foreach_range(session, state, params,
                            lambda: self._execute_body_nodes(body_nodes, session, state, run.id))
                    
                    # 标记body节点已执行
                    executed.update(body_node_ids)
                else:
                    fn = self._resolve_node_fn(ntype)
                    fn(session, state, params)
                
                executed.add(node_id)
                logger.info(f"[工作流] 标准格式节点成功 id={node_id} type={ntype}")
                await self._publish(run.id, f"event: step_succeeded\ndata: {ntype}\n\n")
                
                # 执行后续节点（非ForEach的情况）
                if ntype not in ("List.ForEach", "List.ForEachRange"):
                    for next_id in successors.get(node_id, []):
                        if next_id not in executed:
                            # 检查前置依赖是否都已完成
                            deps = dependencies.get(next_id, [])
                            if all(dep in executed for dep in deps):
                                await execute_node(next_id)
                
            except Exception as e:  # noqa: BLE001
                logger.exception(f"[工作流] 标准格式节点失败 id={node_id} type={ntype} err={e}")
                await self._publish(run.id, f"event: step_failed\ndata: {ntype}: {e}\n\n")
                raise
        
        # 执行起始节点
        for start_id in start_nodes:
            await execute_node(start_id)
        
        # 保存结果
        await self._save_execution_result(session, run, state)

    def _execute_body_nodes(self, body_nodes: List[dict], session, state, run_id: int):
        """同步执行body节点（用于ForEach回调）"""
        for bn in body_nodes:
            ntype = bn.get("type")
            params = bn.get("params") or {}
            logger.info(f"[工作流] ForEach body节点 type={ntype}")
            try:
                fn = self._resolve_node_fn(ntype)
                fn(session, state, params)
            except Exception as e:  # noqa: BLE001
                logger.exception(f"[工作流] ForEach body节点失败 type={ntype} err={e}")
                raise

    async def _execute_legacy_format(self, session: Session, workflow: Workflow, run: WorkflowRun, raw_nodes: List[dict]) -> None:
        """执行旧格式的工作流（保持向后兼容）"""
        nodes: List[dict] = self._canonicalize(raw_nodes)
        state: Dict[str, Any] = {"scope": run.scope_json or {}, "touched_card_ids": set()}
        logger.info(f"[工作流] 开始执行旧格式 run_id={run.id} workflow_id={workflow.id} nodes={len(nodes)}")

        def run_body(body_nodes: List[dict]):
            for bn in body_nodes:
                ntype = bn.get("type")
                params = bn.get("params") or {}
                logger.info(f"[工作流] 旧格式节点开始 type={ntype}")
                if ntype == "List.ForEach":
                    body = list((bn.get("body") or []))
                    builtin_nodes.node_list_foreach(session, state, params, lambda: run_body(body))
                    logger.info("[工作流] 旧格式节点结束 List.ForEach")
                    continue
                if ntype == "List.ForEachRange":
                    body = list((bn.get("body") or []))
                    builtin_nodes.node_list_foreach_range(session, state, params, lambda: run_body(body))
                    logger.info("[工作流] 旧格式节点结束 List.ForEachRange")
                    continue
                fn = self._resolve_node_fn(ntype)
                asyncio.get_event_loop().create_task(self._publish(run.id, f"event: step_started\ndata: {ntype}\n\n"))
                try:
                    fn(session, state, params)
                    logger.info(f"[工作流] 旧格式节点成功 type={ntype}")
                    asyncio.get_event_loop().create_task(self._publish(run.id, f"event: step_succeeded\ndata: {ntype}\n\n"))
                except Exception as e:  # noqa: BLE001
                    logger.exception(f"[工作流] 旧格式节点失败 type={ntype} err={e}")
                    asyncio.get_event_loop().create_task(self._publish(run.id, f"event: step_failed\ndata: {ntype}: {e}\n\n"))
                    raise

        run_body(nodes)
        await self._save_execution_result(session, run, state)

    async def _save_execution_result(self, session: Session, run: WorkflowRun, state: dict) -> None:
        """保存执行结果"""
        logger.info(f"[工作流] 执行完毕 run_id={run.id}")
        try:
            touched = list(sorted({int(x) for x in (state.get("touched_card_ids") or set())}))
            run.summary_json = {**(run.summary_json or {}), "affected_card_ids": touched}
            session.add(run)
            session.commit()
        except Exception:
            logger.exception("[工作流] 汇总受影响卡片ID失败")

    # ---------------- run ----------------
    def run(self, session: Session, run: WorkflowRun) -> None:
        if run.id in self._run_tasks:
            return

        async def _runner():
            run_id = run.id
            # 确保事件队列已存在
            self._ensure_queue(run_id)
            await self._publish(run_id, "event: step_started\n\n")
            try:
                run_db: WorkflowRun = session.exec(select(WorkflowRun).where(WorkflowRun.id == run_id)).one()
                run_db.status = "running"
                run_db.started_at = datetime.utcnow()
                session.add(run_db)
                session.commit()

                workflow = session.exec(select(Workflow).where(Workflow.id == run.workflow_id)).one()
                await self._publish(run_id, "event: log\ndata: 开始执行DSL...\n\n")
                logger.info(f"[工作流] run启动 run_id={run_id} workflow_id={workflow.id}")
                await self._execute_dsl(session, workflow, run)

                run_db = session.exec(select(WorkflowRun).where(WorkflowRun.id == run_id)).one()
                run_db.status = "succeeded"
                run_db.finished_at = datetime.utcnow()
                session.add(run_db)
                session.commit()
                # 发布包含受影响卡片ID的完成事件
                try:
                    affected = []
                    try:
                        affected = list(sorted({int(x) for x in (run_db.summary_json or {}).get("affected_card_ids", [])}))
                    except Exception:
                        affected = []
                    payload = {"status": "succeeded", "affected_card_ids": affected}
                    import json as _json
                    await self._publish(run_id, f"event: run_completed\ndata: {_json.dumps(payload, ensure_ascii=False)}\n\n")
                except Exception:
                    await self._publish(run_id, "event: run_completed\ndata: {\"status\":\"succeeded\"}\n\n")
            except asyncio.CancelledError:
                run_db = session.exec(select(WorkflowRun).where(WorkflowRun.id == run_id)).one()
                run_db.status = "cancelled"
                run_db.finished_at = datetime.utcnow()
                session.add(run_db)
                session.commit()
                await self._publish(run_id, "event: run_completed\ndata: {\"status\":\"cancelled\"}\n\n")
                raise
            except Exception as e:  # noqa: BLE001
                logger.exception(f"[工作流] run失败 run_id={run_id} err={e}")
                run_db = session.exec(select(WorkflowRun).where(WorkflowRun.id == run_id)).one()
                run_db.status = "failed"
                run_db.finished_at = datetime.utcnow()
                run_db.error_json = {"message": str(e)}
                session.add(run_db)
                session.commit()
                # 失败也尽量附带受影响卡片，便于前端选择性刷新
                try:
                    affected = []
                    try:
                        affected = list(sorted({int(x) for x in (run_db.summary_json or {}).get("affected_card_ids", [])}))
                    except Exception:
                        affected = []
                    payload = {"status": "failed", "affected_card_ids": affected, "error": str(e)}
                    import json as _json
                    await self._publish(run_id, f"event: run_completed\ndata: {_json.dumps(payload, ensure_ascii=False)}\n\n")
                except Exception:
                    await self._publish(run_id, "event: run_completed\ndata: {\"status\":\"failed\"}\n\n")
            finally:
                await self._close_queue(run_id)

        task = self._background_run(lambda: _runner(), run.id)
        if task is not None:
            self._run_tasks[run.id] = task

    def cancel(self, run_id: int) -> bool:
        task = self._run_tasks.get(run_id)
        if task and not task.done():
            task.cancel()
            return True
        return False


engine = LocalAsyncEngine()