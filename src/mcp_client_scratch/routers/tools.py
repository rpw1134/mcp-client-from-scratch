from fastapi import APIRouter, Depends
from ..dependencies.app_state import get_client_manager, get_vector_store
from ..classes.ClientManager import ClientManager
from ..classes.VectorStore import VectorStore

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("/")
async def list_all_tools(client_manager: ClientManager = Depends(get_client_manager)) -> dict:
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
async def get_tool_embeddings(vector_store: VectorStore = Depends(get_vector_store)) -> dict:
    """Get hashes for all tools in the vector store."""
    try:
        tools_embeddings = await vector_store.get_tool_hashes()
        return {"tool_embeddings": tools_embeddings}
    except Exception as e:
        return {"error": str(e)}
