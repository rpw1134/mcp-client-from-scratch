from fastapi import APIRouter, Depends
from ..dependencies.app_state import get_client_manager, get_vector_store

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
    
@router.get("/tools/embeddings")
async def get_tool_embeddings(vector_store = Depends(get_vector_store)) -> dict:
    """Get embeddings for all tools in the vector store."""
    try:
        tools_embeddings = await vector_store.get_all_tool_embeddings()
        return {"tool_embeddings": tools_embeddings}
    except Exception as e:
        return {"error": str(e)}
