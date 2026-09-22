from fastapi import APIRouter

api_router = APIRouter()


@api_router.get("/status", tags=["Status"])
async def status():
    return {"status": "ok", "message": "Prism API is running"}
