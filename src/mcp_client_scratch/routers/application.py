from fastapi import APIRouter, Depends, Query
from ..dependencies.connections import get_client_manager, get_session_store, get_redis_client

router = APIRouter(prefix="/application", tags=["app"])

@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint for application router."""
    return {"status": "healthy", "service": "mcp-client-application"}

@router.get("/servers")
async def list_servers(client_manager = Depends(get_client_manager)) -> dict:
    """List all configured MCP servers. For running servers, see list_running_servers."""
    try:
        servers = client_manager.get_all_servers()
        return {"servers": list(servers.keys())}
    except Exception as e:
        return {"error": str(e)}

@router.get("/servers/static-servers")
async def list_static_servers(client_manager = Depends(get_client_manager)) -> dict:
    """List all statically configured MCP servers. For running static servers, see list_running_dynamic_servers."""
    try:
        static_servers = client_manager._static_servers
        return {"static_servers": list(static_servers.keys())}
    except Exception as e:
        return {"error": str(e)}

@router.get("/servers/dynamic-servers")
async def list_dynamic_servers(client_manager = Depends(get_client_manager)) -> dict:
    """List all dynamically configured MCP servers. For running static servers, see list_running_static_servers."""
    try:
        dynamic_servers = client_manager._dynamic_servers
        return {"dynamic_servers": list(dynamic_servers.keys())}
    except Exception as e:
        return {"error": str(e)}

@router.get("/clients/tools")
async def list_server_tools(client_manager = Depends(get_client_manager)) -> dict:
    """List available tools for running MCP clients."""
    try:
        running_clients = client_manager.get_running_clients()
        all_tools = {}
        for name, client in running_clients.items():
            all_tools[name] = client.tools
        return {"tools": all_tools}
    except Exception as e:
        return {"error": str(e)}

@router.get("/clients/running-clients/tools")
async def list_running_server_tools(client_manager = Depends(get_client_manager)) -> dict:
    """List available tools for running MCP clients."""
    try:
        running_clients = client_manager.get_running_clients()
        all_tools = {}
        for name, client in running_clients.items():
            all_tools[name] = client.tools
        return {"running_clients_tools": all_tools}
    except Exception as e:
        return {"error": str(e)}
    
@router.get("/clients/failed-clients/tools")
async def list_failed_server_tools(client_manager = Depends(get_client_manager)) -> dict:
    """List available tools for failed MCP clients."""
    try:
        failed_clients = client_manager.get_failed_clients()
        all_tools = {}
        for name, client in failed_clients.items():
            if isinstance(client, Exception):
                all_tools[name] = str(client)
            else:
                all_tools[name] = client.tools
        return {"failed_clients_tools": all_tools}
    except Exception as e:
        return {"error": str(e)}

@router.get("/clients/{client_name}/tools")
async def get_server_tools(client_name: str, client_manager = Depends(get_client_manager)) -> dict:
    """Get tools for a specific MCP server."""
    try:
        client = client_manager.get_client(client_name)
        if not client:
            return {"error": f"Server '{client_name}' not found or not running"}
        return {"server": client_name, "tools": client.tools}
    except Exception as e:
        return {"error": str(e)}

@router.get("/clients")
async def list_clients(client_manager = Depends(get_client_manager)) -> dict:
    """List all clients (running and failed)."""
    #TODO CLIENT STR REPRESENATION
    try:
        all_clients = client_manager.get_clients()
        return {"clients": list(all_clients.keys())}
    except Exception as e:
        return {"error": str(e)}
    
@router.get("/clients/running-clients")
async def get_running_clients(client_manager = Depends(get_client_manager)) -> dict:
    """Get all running clients."""
    try:
        running = client_manager.get_running_clients()
        return {"running_clients": list(running.keys())}
    except Exception as e:
        return {"error": str(e)}
    
@router.get("/clients/failed-clients")
async def get_failed_clients(client_manager = Depends(get_client_manager)) -> dict:
    """Get all failed clients."""
    try:
        failed = client_manager.get_failed_clients()
        return {"failed_clients": list(failed.keys())}
    except Exception as e:
        return {"error": str(e)}
    
@router.get("/clients/{client_name}")
async def get_client_status_by_name(client_name: str, client_manager = Depends(get_client_manager)) -> dict:
    """Get status of a specific client by name."""
    try:
        client = client_manager.get_client(client_name)
        if not client:
            return {"error": f"Client '{client_name}' not found"}
        status = {
            "name": client_name,
            "status": "running" if not isinstance(client, Exception) else "failed",
            "tools": client.tools if not isinstance(client, Exception) else str(client)
        }
        return {"client_status": status}
    except Exception as e:
        return {"error": str(e)}
    
@router.get("/clients/client-statuses")
async def get_client_status(client_manager = Depends(get_client_manager)) -> dict:
    """Get status of all clients (running and failed)."""
    try:
        status = client_manager.get_client_status()
        return {"client_status": status}
    except Exception as e:
        return {"error": str(e)}
    
@router.get("/clients/{client_name}/status")
async def get_client_status_individual(client_name: str, client_manager = Depends(get_client_manager)) -> dict:
    """Get status of a specific client by name."""
    try:
        status = client_manager.get_client_status()
        if client_name not in status:
            return {"error": f"Client '{client_name}' not found"}
        return {"client_status": {client_name: status[client_name]}}
    except Exception as e:
        return {"error": str(e)}


