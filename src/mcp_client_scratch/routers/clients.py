from fastapi import APIRouter, Depends
from ..dependencies.app_state import get_client_manager
from fastapi import Query
from typing import Literal

router = APIRouter(prefix="/clients", tags=["clients"])


@router.get("/")
async def list_clients(client_manager = Depends(get_client_manager), status = Query(Literal["failed", "running"])) -> dict:
    """List all MCP clients, optionally filtered by status."""
    try:
        print(status)
        all_clients = client_manager.get_clients()
        if status == "failed":
            return {"clients": [name for name, client in all_clients.items() if isinstance(client, Exception)]}
        elif status == "running":
            return {"clients": [name for name, client in all_clients.items() if not isinstance(client, Exception)]}
        return {"clients": list(all_clients.keys())}
    except Exception as e:
        return {"error": str(e)}

@router.get("/running")
async def get_running_clients(client_manager = Depends(get_client_manager)) -> dict:
    """Get all running clients."""
    try:
        running = client_manager.get_running_clients()
        return {"running_clients": list(running.keys())}
    except Exception as e:
        return {"error": str(e)}

@router.get("/failed")
async def get_failed_clients(client_manager = Depends(get_client_manager)) -> dict:
    """Get all failed clients."""
    try:
        failed = client_manager.get_failed_clients()
        return {"failed_clients": list(failed.keys())}
    except Exception as e:
        return {"error": str(e)}

@router.get("/{client_name}")
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

@router.get("/{client_name}/status")
async def get_client_status_individual(client_name: str, client_manager = Depends(get_client_manager)) -> dict:
    """Get detailed status of a specific client by name."""
    try:
        status = client_manager.get_client_status()
        if client_name not in status:
            return {"error": f"Client '{client_name}' not found"}
        return {"client_status": {client_name: status[client_name]}}
    except Exception as e:
        return {"error": str(e)}

@router.get("/{client_name}/tools")
async def get_client_tools(client_name: str, client_manager = Depends(get_client_manager)) -> dict:
    """Get tools for a specific MCP client."""
    try:
        client = client_manager.get_client(client_name)
        if not client:
            return {"error": f"Client '{client_name}' not found or not running"}
        return {"client": client_name, "tools": client.tools}
    except Exception as e:
        return {"error": str(e)}
