from fastapi import APIRouter


api_router = APIRouter()
# Add routers here:
# api_router.include_router(some_router, prefix="/v1")


__all__ = [
    "api_router",
]
