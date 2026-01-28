from contextvars import ContextVar
from typing import List

# 定义上下文变量，用于存储当前请求触发的工作流运行ID列表
_workflow_runs_ctx: ContextVar[List[int]] = ContextVar("workflow_runs_ctx", default=[])

def init_workflow_context():
    """初始化上下文（在每个请求开始时调用）"""
    _workflow_runs_ctx.set([])

def add_triggered_run_id(run_id: int):
    """添加触发的运行ID"""
    current_list = _workflow_runs_ctx.get()
    # ContextVar 的 get 返回的是同一个列表对象的引用（因为 default 只是初始值，set 之后是新的）
    # 但为了安全起见，我们应该确保我们在修改当前的列表
    # 注意：如果从未调用过 set，get() 会返回 default 的那个空列表。
    # 为了避免跨请求污染（虽然 default 是共享的），中间件必须显式 set([])。
    # 这里我们假设中间件已经初始化了新的空列表。
    current_list.append(run_id)

def get_triggered_run_ids() -> List[int]:
    """获取所有触发的运行ID"""
    return _workflow_runs_ctx.get()

def clear_workflow_context():
    """清理上下文"""
    _workflow_runs_ctx.set([])
