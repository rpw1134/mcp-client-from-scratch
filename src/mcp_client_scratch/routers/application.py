from fastapi import APIRouter, Depends, Query
from ..dependencies.connections import get_client_manager, get_session_store, get_redis_client

router = APIRouter(prefix="/application", tags=["app"])

@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint for application router."""
    return {"status": "healthy", "service": "mcp-client-application"}

@router.get("/servers")
async def list_servers(client_manager = Depends(get_client_manager)) -> dict:
    """List all configured MCP servers."""
    try:
        servers = client_manager.get_all_servers()
        return {"servers": list(servers.keys())}
    except Exception as e:
        return {"error": str(e)}

@router.get("/servers/static")
async def list_static_servers(client_manager = Depends(get_client_manager)) -> dict:
    """List all statically configured MCP servers."""
    try:
        static_servers = client_manager._static_servers
        return {"static_servers": list(static_servers.keys())}
    except Exception as e:
        return {"error": str(e)}

@router.get("/servers/dynamic")
async def list_dynamic_servers(client_manager = Depends(get_client_manager)) -> dict:
    """List all dynamically configured MCP servers."""
    try:
        dynamic_servers = client_manager._dynamic_servers
        return {"dynamic_servers": list(dynamic_servers.keys())}
    except Exception as e:
        return {"error": str(e)}

@router.get("/servers/tools")
async def list_server_tools(client_manager = Depends(get_client_manager)) -> dict:
    """List available tools for all MCP servers."""
    try:
        running_clients = client_manager.get_running_clients()
        all_tools = {}
        for name, client in running_clients.items():
            all_tools[name] = client.tools
        return {"tools": all_tools}
    except Exception as e:
        return {"error": str(e)}

@router.get("/servers/{server_name}/tools")
async def get_server_tools(server_name: str, client_manager = Depends(get_client_manager)) -> dict:
    """Get tools for a specific MCP server."""
    try:
        client = client_manager.get_client(server_name)
        if not client:
            return {"error": f"Server '{server_name}' not found or not running"}
        return {"server": server_name, "tools": client.tools}
    except Exception as e:
        return {"error": str(e)}

@router.get("/clients/status")
async def get_client_status(client_manager = Depends(get_client_manager)) -> dict:
    """Get status of all clients (running and failed)."""
    try:
        status = client_manager.get_client_status()
        return {"client_status": status}
    except Exception as e:
        return {"error": str(e)}


