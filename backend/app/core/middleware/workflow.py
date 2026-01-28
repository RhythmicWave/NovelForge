from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from app.core.workflow_context import init_workflow_context, get_triggered_run_ids

class WorkflowHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. 初始化上下文（确保每个请求都有独立的列表）
        init_workflow_context()
        
        # 2.处理请求
        response = await call_next(request)
        
        # 3. 检查上下文并注入 Header
        run_ids = get_triggered_run_ids()
        if run_ids:
            # 如果已有该 Header（极少见），追加
            existing = response.headers.get("X-Workflows-Started")
            if existing:
                new_ids = f"{existing},{','.join(map(str, run_ids))}"
                response.headers["X-Workflows-Started"] = new_ids
            else:
                response.headers["X-Workflows-Started"] = ",".join(map(str, run_ids))
                
        return response
