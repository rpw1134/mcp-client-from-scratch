from fastapi import APIRouter

router = APIRouter(prefix="/application", tags=["app"])


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint for application router."""
    return {"status": "healthy", "service": "mcp-client-application"}


