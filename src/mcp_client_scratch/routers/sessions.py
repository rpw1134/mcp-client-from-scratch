from fastapi import APIRouter, Depends
from ..dependencies.app_state import get_vector_store, get_openai_client, get_session_store
from ..schemas.session import ModelMessage
from ..schemas.requests import ChatRequest
from ..classes.VectorStore import VectorStore
from ..classes.OpenAIClient import OpenAIClient
from ..classes.SessionStore import SessionStore
from ..utils.constants import SYSTEM_PROMPT_BASE
from openai.types.chat import ChatCompletionMessageParam
from fastapi import Query
from typing import cast
import json

router = APIRouter(prefix="/sessions", tags=["sessions"])

@router.get("/health")
async def agent_health_check() -> dict:
    """Health check endpoint for the sessions router."""
    return {"status": "healthy", "service": "agent"}

@router.post("/")
async def create_agent_session(request: dict, session_store: SessionStore = Depends(get_session_store )) -> dict:
    new_session_id = session_store.create_session()
    return {"new_session_id": new_session_id}

@router.post("/{session_id}/agent/request")
async def handle_agent_request(request: ChatRequest, session_id, vector_store: VectorStore = Depends(get_vector_store), openai_client: OpenAIClient = Depends(get_openai_client), session_store: SessionStore = Depends(get_session_store))-> dict:
    req = request.message
    new_message = ModelMessage(role="user", content=req)
    session_store.post_message(session_id, new_message)
    session_messages = session_store.get_session_messages(session_id)
    relevant_tools = json.dumps((await vector_store.query_similar_tools(req,3)))
    session_messages+=[ModelMessage(role="system", content=f"{SYSTEM_PROMPT_BASE} {relevant_tools}")]
    response_message = await openai_client.tool_selection_request(system_prompt=f"{SYSTEM_PROMPT_BASE} {relevant_tools}", messages = [cast(ChatCompletionMessageParam, message) for message in session_messages])
    return {"res":response_message}