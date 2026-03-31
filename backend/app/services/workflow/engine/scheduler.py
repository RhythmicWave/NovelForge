"""工作流调度器 - 管理工作流运行队列"""

import asyncio
from typing import Dict, List, Tuple, Any
from loguru import logger


class WorkflowScheduler:
    """工作流调度器

    职责：
    - 管理运行队列
    - 控制并发运行数
    - 优先级调度（数字越小优先级越高）
    """

    def __init__(self, max_concurrent_runs: int = 5):
        self.max_concurrent_runs = max_concurrent_runs
        self.running_runs: Dict[int, asyncio.Task] = {}  # run_id -> task
        # 用列表模拟优先级队列，入队后按 priority 排序取出
        self._pending: List[Tuple[int, int, Any]] = []  # [(priority, run_id, coro), ...]
        self._cancelled_ids: set = set()  # 被取消的排队 run_id

    async def schedule_run(
        self,
        run_id: int,
        executor_coro,
        priority: int = 0
    ) -> None:
        """调度工作流运行

        Args:
            run_id: 运行ID
            executor_coro: 执行器协程
            priority: 优先级（数字越小优先级越高）
        """
        if len(self.running_runs) < self.max_concurrent_runs:
            # 直接启动
            await self._start_run(run_id, executor_coro)
        else:
            # 加入队列等待
            logger.info(
                f"[Scheduler] 运行加入等待队列: run_id={run_id}, "
                f"priority={priority}"
            )
            self._pending.append((priority, run_id, executor_coro))
            # 按 priority 升序排列（越小越优先）
            self._pending.sort(key=lambda x: x[0])

    async def _start_run(self, run_id: int, executor_coro) -> None:
        """启动运行"""
        logger.info(f"[Scheduler] 启动运行: run_id={run_id}")

        # 创建任务
        task = asyncio.create_task(self._run_with_cleanup(run_id, executor_coro))
        self.running_runs[run_id] = task

    async def _run_with_cleanup(self, run_id: int, executor_coro) -> None:
        """执行运行并清理"""
        try:
            await executor_coro
        finally:
            # 清理
            if run_id in self.running_runs:
                del self.running_runs[run_id]

            logger.info(
                f"[Scheduler] 运行完成: run_id={run_id}, "
                f"当前运行数={len(self.running_runs)}"
            )

            # 启动队列中的下一个
            await self._start_next_from_queue()

    async def _start_next_from_queue(self) -> None:
        """从队列中启动下一个运行（按优先级顺序）"""
        while self._pending and len(self.running_runs) < self.max_concurrent_runs:
            priority, run_id, executor_coro = self._pending.pop(0)

            # 跳过已被取消的
            if run_id in self._cancelled_ids:
                self._cancelled_ids.discard(run_id)
                logger.info(f"[Scheduler] 跳过已取消的排队运行: run_id={run_id}")
                continue

            logger.info(
                f"[Scheduler] 从队列启动运行: run_id={run_id}, priority={priority}"
            )
            await self._start_run(run_id, executor_coro)
            return

    def cancel_run(self, run_id: int) -> bool:
        """取消运行（支持取消运行中和排队中的任务）

        Args:
            run_id: 运行ID

        Returns:
            是否成功取消
        """
        # 先尝试取消正在运行的
        if run_id in self.running_runs:
            task = self.running_runs[run_id]
            task.cancel()
            logger.info(f"[Scheduler] 取消运行中的任务: run_id={run_id}")
            return True

        # 再尝试取消排队中的
        for item in self._pending:
            if item[1] == run_id:
                self._cancelled_ids.add(run_id)
                logger.info(f"[Scheduler] 取消排队中的任务: run_id={run_id}")
                return True

        return False

    def get_running_count(self) -> int:
        """获取当前运行数"""
        return len(self.running_runs)

    def get_pending_count(self) -> int:
        """获取等待队列长度"""
        return len(self._pending)

    def is_running(self, run_id: int) -> bool:
        """检查运行是否正在执行"""
        return run_id in self.running_runs
