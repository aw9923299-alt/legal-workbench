from fastapi import APIRouter, Depends

from legal_workbench.api.dependencies import get_request_actor
from legal_workbench.api.routes.agents import router as agents_router
from legal_workbench.api.routes.auth import router as auth_router
from legal_workbench.api.routes.candidates import router as candidates_router
from legal_workbench.api.routes.dashboard import router as dashboard_router
from legal_workbench.api.routes.events import router as events_router
from legal_workbench.api.routes.health import router as health_router
from legal_workbench.api.routes.integrations import router as integrations_router
from legal_workbench.api.routes.matter_update_proposals import (
    router as matter_update_proposals_router,
)
from legal_workbench.api.routes.matters import router as matters_router
from legal_workbench.api.routes.messages import router as messages_router
from legal_workbench.api.routes.outbox import router as outbox_router
from legal_workbench.api.routes.reviews import router as reviews_router
from legal_workbench.api.routes.system import router as system_router
from legal_workbench.api.routes.work_items import router as work_items_router

api_router = APIRouter()
authenticated = [Depends(get_request_actor)]
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(agents_router, dependencies=authenticated)
api_router.include_router(candidates_router, dependencies=authenticated)
api_router.include_router(dashboard_router, dependencies=authenticated)
api_router.include_router(matters_router, dependencies=authenticated)
api_router.include_router(matter_update_proposals_router, dependencies=authenticated)
api_router.include_router(work_items_router, dependencies=authenticated)
api_router.include_router(reviews_router, dependencies=authenticated)
api_router.include_router(integrations_router)
api_router.include_router(outbox_router, dependencies=authenticated)
api_router.include_router(system_router, dependencies=authenticated)
api_router.include_router(messages_router, dependencies=authenticated)
api_router.include_router(events_router, dependencies=authenticated)
