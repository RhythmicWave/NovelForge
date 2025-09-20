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
from sqlmodel import SQLModel, Session, select

from app.api.router import api_router
from app.db.session import engine
from app.db import models
from app.bootstrap.init_app import init_prompts, create_default_card_types
# 知识库初始化
from app.bootstrap.init_app import init_knowledge
from app.bootstrap.init_app import init_reserved_project
from app.bootstrap.init_app import init_workflows
 # 初始化项目模板
from app.bootstrap.init_app import init_project_templates

def init_db():
    models.SQLModel.metadata.create_all(engine)

# 创建所有表
# models.Base.metadata.create_all(bind=engine)

from contextlib import asynccontextmanager

# 使用 lifespan 事件处理器替代 on_event
@asynccontextmanager
async def lifespan(app):
    # 启动时执行
    # 确保所有表存在（开发阶段可用；生产建议通过 Alembic 迁移）
    models.SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        init_prompts(session)
        create_default_card_types(session)
        # 初始化知识库
        init_knowledge(session)
        # 初始化系统预设项目模板（依赖卡片类型）
        init_project_templates(session)
        # 初始化保留项目
        init_reserved_project(session)
        # 初始化内置工作流
        init_workflows(session)
    yield
    # 关闭时可添加清理逻辑（如有需要）

# 创建 FastAPI 应用实例，注册 lifespan
app = FastAPI(
    title="NovelForge API",
    version="1.0.0",
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# 设置CORS中间件，允许所有来源的请求
# 这在开发环境中很方便，但在生产环境中应该更严格
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有方法
    allow_headers=["*"],  # 允许所有头部
    expose_headers=["X-Workflows-Started"],  # 允许浏览器读取此自定义响应头
)

# 包含API路由
app.include_router(api_router, prefix="/api")


@app.get("/")
def read_root():
    return {"message": "Welcome to NovelCreationEditor API"}

if __name__ == "__main__":
    import uvicorn
    # 添加reload=True，这样当代码修改时会自动重新加载
    # 配置更短的优雅关闭时间，便于 Ctrl+C 快速退出
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        timeout_graceful_shutdown=1,
    )

