from fastapi import APIRouter
from ..classes.Agent import Agent
from fastapi import Depends
from ..dependencies.app_state import get_agent
from ..schemas.requests import ChatRequest
import logging

router = APIRouter(prefix="/agent", tags=["agent"])
logger = logging.getLogger("uvicorn.error")

@router.post("/")
async def create_agent_session(agent: Agent = Depends(get_agent)) -> dict:
    new_session_id = agent.create_new_agent_session()
    return {"new_session_id": new_session_id}

@router.post("/request")
async def handle_agent_request(request: ChatRequest, agent: Agent = Depends(get_agent))-> dict:
    # almost working, need to tweak the system prompt to not call a tool unless ALL necessary arguments are accessible (seems to be more model dependant), need to remove base tools from the clients so that they aren't considered in the embedding stuff, and need to find a way to add context of previous tools that are waiting on information so that the agent can populate the field afterwards.
    user_message = request.message
    agent_res = await agent.process_request(user_message)
    logger.info(f"Agent response: {agent_res["res"]}")
    response = await agent.call_tool(agent_res["res"])
    return {"response": response}