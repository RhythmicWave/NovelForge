import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from app.api.router import api_router
from app.core import settings
from app.core.startup import startup, shutdown
from app.core.middleware.workflow import WorkflowHeaderMiddleware


@asynccontextmanager
async def lifespan(app):
    startup()
    try:
        from app.db.session import engine
        from sqlmodel import Session
        from app.services.workflow.cleanup import cleanup_expired_runs
        with Session(engine) as session:
            cleanup_expired_runs(session)
    except Exception as e:
        print(f"Startup cleanup failed: {e}")
    yield
    shutdown()


app = FastAPI(
    title=f"{settings.app.app_name} API",
    version=settings.app.app_version,
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan,
)

app.add_middleware(WorkflowHeaderMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.app.get_cors_origins_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Workflows-Started"],
)

app.include_router(api_router, prefix=settings.app.api_prefix)

# Serve frontend SPA — must be mounted AFTER API routes
app.mount('/', StaticFiles(directory='static', html=True), name='static')

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=54321)
