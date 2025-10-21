from fastapi import APIRouter, Depends
from ..dependencies.app_state import get_client_manager

router = APIRouter(prefix="/servers", tags=["servers"])


@router.get("/")
async def list_servers(client_manager = Depends(get_client_manager)) -> dict:
    """List all configured MCP servers."""
    try:
        servers = client_manager.get_all_servers()
        return {"servers": list(servers.keys())}
    except Exception as e:
        return {"error": str(e)}

@router.get("/static/")
async def list_static_servers(client_manager = Depends(get_client_manager)) -> dict:
    """List all statically configured MCP servers."""
    try:
        static_servers = client_manager._static_servers
        return {"static_servers": list(static_servers.keys())}
    except Exception as e:
        return {"error": str(e)}

@router.get("/dynamic/")
async def list_dynamic_servers(client_manager = Depends(get_client_manager)) -> dict:
    """List all dynamically configured MCP servers."""
    try:
        dynamic_servers = client_manager._dynamic_servers
        return {"dynamic_servers": list(dynamic_servers.keys())}
    except Exception as e:
        return {"error": str(e)}
