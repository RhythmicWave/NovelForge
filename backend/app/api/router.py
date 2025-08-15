
from fastapi import APIRouter
from app.api.endpoints import projects, llm_configs, ai, prompts, cards
from app.api.endpoints import outputs
from app.api.endpoints import context as context_ep
from app.api.endpoints import memory as memory_ep
from app.api.endpoints import foreshadow as foreshadow_ep
from app.api.endpoints import knowledge as knowledge_ep

api_router = APIRouter()
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(llm_configs.router, prefix="/llm-configs", tags=["llm-configs"])

api_router.include_router(ai.router, prefix="/ai", tags=["ai"])
api_router.include_router(prompts.router, prefix="/prompts", tags=["prompts"]) 
api_router.include_router(cards.router, prefix="", tags=["cards"])
api_router.include_router(outputs.router, prefix="/output-models", tags=["output-models"]) 
api_router.include_router(context_ep.router, prefix="/context", tags=["context"]) 
api_router.include_router(memory_ep.router, prefix="/memory", tags=["memory"]) 
api_router.include_router(foreshadow_ep.router, prefix="/foreshadow", tags=["foreshadow"]) 
api_router.include_router(knowledge_ep.router, prefix="/knowledge", tags=["knowledge"]) 