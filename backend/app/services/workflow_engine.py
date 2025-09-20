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
            "Card.Read": builtin_nodes.node_card_read,
            "Card.ModifyContent": builtin_nodes.node_card_modify_content,
            "Card.UpsertChildByTitle": builtin_nodes.node_card_upsert_child_by_title,
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
        nodes: List[dict] = self._canonicalize(raw_nodes)
        state: Dict[str, Any] = {"scope": run.scope_json or {}, "touched_card_ids": set()}
        logger.info(f"[工作流] 开始执行 run_id={run.id} workflow_id={workflow.id} nodes={len(nodes)} scope={state.get('scope')}")

        def run_body(body_nodes: List[dict]):
            for bn in body_nodes:
                ntype = bn.get("type")
                params = bn.get("params") or {}
                logger.info(f"[工作流] 节点开始 type={ntype} params_keys={list(params.keys())}")
                if ntype == "List.ForEach":
                    body = list((bn.get("body") or []))
                    builtin_nodes.node_list_foreach(session, state, params, lambda: run_body(body))
                    logger.info("[工作流] 节点结束 List.ForEach")
                    continue
                if ntype == "List.ForEachRange":
                    body = list((bn.get("body") or []))
                    builtin_nodes.node_list_foreach_range(session, state, params, lambda: run_body(body))
                    logger.info("[工作流] 节点结束 List.ForEachRange")
                    continue
                fn = self._resolve_node_fn(ntype)
                asyncio.get_event_loop().create_task(self._publish(run.id, f"event: step_started\ndata: {ntype}\n\n"))
                try:
                    fn(session, state, params)
                    logger.info(f"[工作流] 节点成功 type={ntype}")
                    asyncio.get_event_loop().create_task(self._publish(run.id, f"event: step_succeeded\ndata: {ntype}\n\n"))
                except Exception as e:  # noqa: BLE001
                    logger.exception(f"[工作流] 节点失败 type={ntype} err={e}")
                    asyncio.get_event_loop().create_task(self._publish(run.id, f"event: step_failed\ndata: {ntype}: {e}\n\n"))
                    raise

        run_body(nodes)
        logger.info(f"[工作流] 执行完毕 run_id={run.id}")
        # 执行结束时将受影响卡片ID写入 run.summary_json（去重排序）
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