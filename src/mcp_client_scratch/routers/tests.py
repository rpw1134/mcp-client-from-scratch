from fastapi import APIRouter, Depends
from ..dependencies.tests import get_stdio_client, reset_stdio_client
from ..utils.constants import SERVER_URLS
from ..classes.MCPClient import STDIOMCPClient

router = APIRouter(prefix="/tests", tags=["tests"])

@router.get("/health")
async def health_check():
    return {"status": "healthy", "service": "mcp-client-stdios-tests"}

@router.post("/init-stdio")
async def init_stdio_client(stdio_client: STDIOMCPClient = Depends(get_stdio_client)):
    return {"message": "Stdio client initialized"}
    
@router.get("/get-tools-stdio")
async def get_tools_stdio(stdio_client: STDIOMCPClient = Depends(get_stdio_client)):
    try:
        tools_response = await stdio_client.get_tools()
        return tools_response
    except Exception as e:
        return {"error": str(e)}
    
@router.post("/reinit-stdio")
async def reinit_stdio_client(stdio_client: STDIOMCPClient = Depends(get_stdio_client)):
    try:
        reset_stdio_client()
        new_stdio_client = await get_stdio_client()
        return {"message": "Stdio client re-initialized"}
    except Exception as e:
        return {"error": str(e)}

