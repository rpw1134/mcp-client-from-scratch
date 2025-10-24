from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from openai.types.chat import ChatCompletionMessageParam
from typing import cast
import json
from collections import OrderedDict
from ..dependencies.tests import get_stdio_client, reset_stdio_client, get_http_client, reset_http_client
from ..dependencies.app_state import get_session_store
from ..dependencies.tests import get_openai_client, get_vector_store
from ..utils.constants import SYSTEM_PROMPT_BASE, EXECUTE_PAYLOAD_TEMPLATE
from ..classes.MCPClient import STDIOMCPClient, HTTPMCPClient
from ..classes.SessionStore import SessionStore
from ..classes.OpenAIClient import OpenAIClient
from ..classes.VectorStore import VectorStore
from ..schemas.session import ModelMessage
from ..schemas.requests import ChatRequest
from ..utils.parse_responses import parse_tool_arguments, parse_response_for_jrpc

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

@router.post("/stdio/tools/embeddings")
async def batch_embed_tools(
    stdio_client: STDIOMCPClient = Depends(get_stdio_client),
    vector_store: VectorStore = Depends(get_vector_store)
) -> dict:
    """Batch embed all tools from the STDIO client into the vector store."""
    try:
        # Get tools from STDIO client
        tools = stdio_client.tools
        
        if not tools:
            return {"message": "No tools to embed", "count": 0}

        # Batch embed the tools
        await vector_store.batch_embed_tools(tools)

        return {
            "message": "Tools successfully embedded",
            "count": len(tools),
            "tool_names": [tool.get("name", "unnamed") for tool in tools.values()]
        }
    except Exception as e:
        return {"error": str(e)}

@router.get("/stdio/tools/embeddings")
async def query_tools(
    query: str = Query(..., description="Query string to search for similar tools"),
    n_results: int = Query(default=10, description="Number of similar tools to return"),
    vector_store: VectorStore = Depends(get_vector_store)
) -> dict:
    """Query for similar tools using semantic search."""
    try:
        similar_tools = await vector_store.query_similar_tools(query, n_results)

        return {
            "query": query,
            "count": len(similar_tools),
            "tools": similar_tools
        }
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
async def chat(
    session_id: str,
    request: ChatRequest,
    stdio_client: STDIOMCPClient = Depends(get_stdio_client),
    session_store: SessionStore = Depends(get_session_store),
    openai_client: OpenAIClient = Depends(get_openai_client)
) -> dict:
    """Make an AI request and route it to the appropriate handler (native tool or MCP server)."""
    try:
        # Get conversation history
        current_messages: list[ChatCompletionMessageParam] = [
            cast(ChatCompletionMessageParam, {"role": m.role, "content": m.content})
            for m in session_store.get_session_messages(session_id)
        ]

        # Add user message to session
        session_store.post_message(session_id, ModelMessage(role="user", content=request.message))

        # Build messages with current user message
        messages_with_user = [
            *current_messages,
            {"role": "user", "content": request.message}
        ]

        # Get system prompt with available tools
        system_prompt = SYSTEM_PROMPT_BASE + str(stdio_client.tools)

        # Make tool selection request
        ai_response = await openai_client.tool_selection_request(
            messages=messages_with_user,
            system_prompt=system_prompt
        )

        # Store assistant response
        session_store.post_message(session_id, ModelMessage(role="assistant", content=ai_response))

        # Parse response
        response_dict = json.loads(ai_response, object_pairs_hook=OrderedDict)
        if "source" in response_dict and response_dict["source"] == "server":
            response_dict |= EXECUTE_PAYLOAD_TEMPLATE.copy()

        # Route to appropriate handler
        if "jsonrpc" not in response_dict:
            res = await parse_tool_arguments(response_dict)
            return {"type": "FUNC", "details": res}
        res = await stdio_client.send_request(await parse_response_for_jrpc(response_dict))
        return {"type": "MCP", "details": res}
    except Exception as e:
        return {"error": str(e)}

# HTTP Client Test Routes

@router.post("/http-client")
async def init_http_client(http_client: HTTPMCPClient = Depends(get_http_client)) -> dict[str, str]:
    """Initialize the HTTP client."""
    return {"message": "HTTP client initialized", "session_id": http_client.mcp_session_id if http_client.mcp_session_id else "no session id"}

@router.get("/http-client/tools")
async def get_http_tools(http_client: HTTPMCPClient = Depends(get_http_client)) -> dict:
    """Retrieve available tools from the HTTP client."""
    try:
        tools_response = await http_client.get_tools()
        return tools_response
    except Exception as e:
        return {"error": str(e)}

@router.put("/http-client")
async def reinit_http_client() -> dict[str, str]:
    """Re-initialize the HTTP client."""
    try:
        await reset_http_client()
        new_http_client = await get_http_client()
        return {"message": "HTTP client re-initialized", "session_id": new_http_client.mcp_session_id if new_http_client.mcp_session_id else "no session id"}
    except Exception as e:
        return {"error": str(e)}

@router.post("/http-client/sessions/{session_id}/chat")
async def http_chat(
    session_id: str,
    request: ChatRequest,
    http_client: HTTPMCPClient = Depends(get_http_client),
    session_store: SessionStore = Depends(get_session_store),
    openai_client: OpenAIClient = Depends(get_openai_client)
) -> dict:
    """Make an AI request using HTTP client and route it to the appropriate handler (native tool or MCP server)."""
    try:
        # Get conversation history
        current_messages: list[ChatCompletionMessageParam] = [
            cast(ChatCompletionMessageParam, {"role": m.role, "content": m.content})
            for m in session_store.get_session_messages(session_id)
        ]

        # Add user message to session
        session_store.post_message(session_id, ModelMessage(role="user", content=request.message))

        # Build messages with current user message
        messages_with_user = [
            *current_messages,
            {"role": "user", "content": request.message}
        ]

        # Get system prompt with available tools
        system_prompt = SYSTEM_PROMPT_BASE + str(http_client.tools)

        # Make tool selection request
        ai_response = await openai_client.tool_selection_request(
            messages=messages_with_user,
            system_prompt=system_prompt
        )

        # Store assistant response
        session_store.post_message(session_id, ModelMessage(role="assistant", content=ai_response))

        # Parse response
        response_dict = json.loads(ai_response, object_pairs_hook=OrderedDict)
        if "source" in response_dict and response_dict["source"] == "server":
            response_dict |= EXECUTE_PAYLOAD_TEMPLATE.copy()

        # Route to appropriate handler
        if "jsonrpc" not in response_dict:
            res = await parse_tool_arguments(response_dict)
            return {"type": "FUNC", "details": res}
        res = await http_client.send_request(await parse_response_for_jrpc(response_dict))
        return {"type": "MCP", "details": res}
    except Exception as e:
        return {"error": str(e)}


