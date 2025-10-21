from fastapi import APIRouter, Depends
from ..dependencies.connections import get_client_manager

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("/")
async def list_all_tools(client_manager = Depends(get_client_manager)) -> dict:
    """List all available tools across all running MCP clients."""
    try:
        running_clients = client_manager.get_running_clients()
        all_tools = {}
        for name, client in running_clients.items():
            all_tools[name] = client.tools
        return {"tools": all_tools}
    except Exception as e:
        return {"error": str(e)}
