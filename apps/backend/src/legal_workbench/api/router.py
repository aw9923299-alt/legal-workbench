from fastapi import APIRouter

from legal_workbench.api.routes.candidates import router as candidates_router
from legal_workbench.api.routes.health import router as health_router
from legal_workbench.api.routes.integrations import router as integrations_router
from legal_workbench.api.routes.matters import router as matters_router
from legal_workbench.api.routes.outbox import router as outbox_router
from legal_workbench.api.routes.reviews import router as reviews_router
from legal_workbench.api.routes.work_items import router as work_items_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(candidates_router)
api_router.include_router(matters_router)
api_router.include_router(work_items_router)
api_router.include_router(reviews_router)
api_router.include_router(integrations_router)
api_router.include_router(outbox_router)
