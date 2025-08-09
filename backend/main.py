from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel, Session, select

from app.api.router import api_router
from app.db.session import engine
from app.db import models
from app.bootstrap.init_app import init_prompts, create_default_card_types, init_output_models

def init_db():
    models.SQLModel.metadata.create_all(engine)

# 创建所有表
# models.Base.metadata.create_all(bind=engine)

# 创建 FastAPI 应用实例
app = FastAPI(
    title="NovelForge API",
    version="1.0.0",
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc"
)

# 设置CORS中间件，允许所有来源的请求
# 这在开发环境中很方便，但在生产环境中应该更严格
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有方法
    allow_headers=["*"],  # 允许所有头部
)

# 包含API路由
app.include_router(api_router, prefix="/api")

@app.on_event("startup")
def on_startup():
    # 数据库表的创建和迁移应完全由Alembic管理
    # init_db() 
    
    # 初始化默认提示词、输出模型、默认卡片类型
    with Session(engine) as session:
        init_prompts(session)
        init_output_models(session)
        create_default_card_types(session)

@app.get("/")
def read_root():
    return {"message": "Welcome to NovelCreationEditor API"}

if __name__ == "__main__":
    import uvicorn
    # 添加reload=True，这样当代码修改时会自动重新加载
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
