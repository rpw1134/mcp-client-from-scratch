from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from ..dependencies.tests import get_stdio_client, reset_stdio_client
from ..utils.constants import SERVER_URLS
from ..classes.MCPClient import STDIOMCPClient
from ..classes.SessionStore import SessionStore
from ..schemas.session import ModelMessage
from ..utils.make_llm_request import AI_request
from ..schemas.requests import ChatRequest
from ..utils.parse_responses import parse_tool_arguments, parse_response_for_jrpc
from ..dependencies.tests import get_session_store

router = APIRouter(prefix="/tests", tags=["tests"])

@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint for tests router."""
    return {"status": "healthy", "service": "mcp-client-stdios-tests"}

@router.post("/stdio")
async def init_stdio_client(stdio_client: STDIOMCPClient = Depends(get_stdio_client)) -> dict[str, str]:
    """Initialize the STDIO client."""
    return {"message": "Stdio client initialized"}

@router.get("/stdio/tools")
async def get_tools(stdio_client: STDIOMCPClient = Depends(get_stdio_client)) -> dict:
    """Retrieve available tools from the STDIO client."""
    try:
        tools_response = await stdio_client.get_tools()
        return tools_response
    except Exception as e:
        return {"error": str(e)}

@router.put("/stdio")
async def reinit_stdio_client(stdio_client: STDIOMCPClient = Depends(get_stdio_client)) -> dict[str, str]:
    """Re-initialize the STDIO client."""
    try:
        reset_stdio_client()
        new_stdio_client = await get_stdio_client()
        return {"message": "Stdio client re-initialized"}
    except Exception as e:
        return {"error": str(e)}
    
@router.post("/sessions")
async def create_session(session_store: SessionStore = Depends(get_session_store)) -> str:
    return session_store.create_session()

@router.delete("/sessions/{session_id}/messages")
async def clear_session(session_id: str, session_store: SessionStore = Depends(get_session_store)) -> dict[str, str]:
    session_store.clear_session(session_id)
    return {"message": f"Session {session_id} cleared."}

@router.post("/sessions/{session_id}/messages")
async def add_message(session_id: str, message: ChatRequest, role: str = Query(default="user", description="Role of the message sender"), session_store: SessionStore = Depends(get_session_store)) -> dict[str, str]:
    model_message = ModelMessage(
        role=role,
        content=message.message
    )
    session_store.post_message(session_id, model_message)
    return {"message": f"Message added to session {session_id}."}

@router.get("/sessions/{session_id}/messages")
async def get_messages(session_id: str, session_store: SessionStore = Depends(get_session_store)) -> list[ModelMessage]:
    return session_store.get_session_messages(session_id)
    
@router.post("/sessions/{session_id}/chat")
async def chat(session_id: str, request: ChatRequest, stdio_client: STDIOMCPClient = Depends(get_stdio_client), session_store: SessionStore = Depends(get_session_store)) -> dict:
    """Make an AI request and route it to the appropriate handler (native tool or MCP server)."""
    try:
        response = AI_request(stdio_client, session_store, session_id, request.message)
        if "jsonrpc" not in response:
            res = await parse_tool_arguments(response)
            return {"type": "FUNC", "details": res}
        res = await stdio_client.send_request(await parse_response_for_jrpc(response))
        return {"type": "MCP", "details": res}
    except Exception as e:
        return {"error": str(e)}



