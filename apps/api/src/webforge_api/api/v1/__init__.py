from fastapi import APIRouter

from webforge_api.api.v1 import activity, audits, auth, designs, discovery, sources, users

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router)
router.include_router(users.router)
router.include_router(activity.router)
router.include_router(sources.router)
router.include_router(discovery.router)
router.include_router(audits.router)
router.include_router(designs.router)
