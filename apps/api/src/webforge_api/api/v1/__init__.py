from fastapi import APIRouter

from webforge_api.api.v1 import activity, auth, users

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router)
router.include_router(users.router)
router.include_router(activity.router)
