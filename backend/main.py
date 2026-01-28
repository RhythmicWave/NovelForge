import os, sys
from dotenv import load_dotenv

def _load_env_from_nearby():
    candidates = []
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        candidates.append(os.path.join(exe_dir, ".env"))
    backend_dir = os.path.abspath(os.path.dirname(__file__))
    candidates.append(os.path.join(backend_dir, ".env"))
    candidates.append(os.path.join(os.getcwd(), ".env"))
    for p in candidates:
        try:
            if os.path.isfile(p):
                load_dotenv(p, override=False)
        except Exception:
            pass

_load_env_from_nearby()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.api.router import api_router
from app.core import settings
from app.core.startup import startup, shutdown


# 使用 lifespan 事件处理器
@asynccontextmanager
async def lifespan(app):
    # 启动时执行
    startup()
    
    # [Optimize] 启动时清理过期的工作流运行记录
    try:
        from app.db.session import engine
        from sqlmodel import Session
        from app.services.workflow.cleanup import cleanup_expired_runs
        
        with Session(engine) as session:
            cleanup_expired_runs(session)
    except Exception as e:
        print(f"Startup cleanup failed: {e}")
        
    yield
    # 关闭时执行
    shutdown()

# 创建 FastAPI 应用实例，注册 lifespan
app = FastAPI(
    title=f"{settings.app.app_name} API",
    version=settings.app.app_version,
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# 注册工作流 Header 中间件 (在 CORS 之前注册，确保响应头被 CORS 处理)
from app.core.middleware.workflow import WorkflowHeaderMiddleware
app.add_middleware(WorkflowHeaderMiddleware)

# 设置CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.app.get_cors_origins_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Workflows-Started"],
)

# 包含API路由
app.include_router(api_router, prefix=settings.app.api_prefix)


@app.get("/")
def read_root():
    return {
        "message": f"Welcome to {settings.app.app_name} API",
        "version": settings.app.app_version
    }

if __name__ == "__main__":
    import uvicorn
    # 添加reload=True，这样当代码修改时会自动重新加载
    # 配置更短的优雅关闭时间，便于 Ctrl+C 快速退出
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        timeout_graceful_shutdown=1,
    )

