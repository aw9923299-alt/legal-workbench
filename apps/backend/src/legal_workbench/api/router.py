from fastapi import APIRouter

from legal_workbench.api.routes.candidates import router as candidates_router
from legal_workbench.api.routes.health import router as health_router
from legal_workbench.api.routes.matters import router as matters_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(candidates_router)
api_router.include_router(matters_router)
