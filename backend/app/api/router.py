
from fastapi import APIRouter
from app.api.endpoints import projects, llm_configs, chapters, ai, prompts, cards
from app.api.endpoints import outputs

api_router = APIRouter()
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(llm_configs.router, prefix="/llm-configs", tags=["llm-configs"])
api_router.include_router(chapters.router, prefix="/chapters", tags=["chapters"])
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])
api_router.include_router(prompts.router, prefix="/prompts", tags=["prompts"]) 
api_router.include_router(cards.router, prefix="", tags=["cards"])
api_router.include_router(outputs.router, prefix="/output-models", tags=["output-models"]) 