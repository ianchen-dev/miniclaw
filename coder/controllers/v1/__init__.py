from fastapi import APIRouter



api_router = APIRouter()
api_router.include_router(, prefix="/v1")


__all__ = [
    "api_router",
]
