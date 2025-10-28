from ..schemas.session import ModelMessage
from ..schemas.requests import ChatRequest
import json
from openai.types.chat import ChatCompletionMessageParam
from ..utils.constants import SYSTEM_PROMPT_BASE, BASE_TOOLS
from typing import cast
import uuid

class Agent:
    
    # An agent shall be responsible for keeping track of: session context length, current requests that need more information aka tools that are waiting on information, current session. 
    # An agent shall be responsible for summarizing session context if exceeds a context length, removing tools from pending requests after they are fulfilled (or if the requests exceed the ttl)
    
    def __init__(self, session_store, vector_store, openai_client):
        self.session_store = session_store
        self.vector_store = vector_store
        self.openai_client = openai_client
        self.session_id = uuid.uuid4().hex
    
    async def process_request(self, user_message: str):
        new_message = ModelMessage(role="user", content=user_message)
        self.session_store.post_message(self.session_id, new_message)
        session_messages = self.session_store.get_session_messages(self.session_id)
        relevant_tools = await self.vector_store.query_similar_tools(user_message,5)
        for tool in relevant_tools:
            del tool["hash"]
        relevant_tools = json.dumps(relevant_tools)
        response_message = await self.openai_client.tool_selection_request(system_prompt=f"{SYSTEM_PROMPT_BASE} {BASE_TOOLS} {relevant_tools}", messages = [cast(ChatCompletionMessageParam, message) for message in session_messages], model='gpt-4o')
        self.session_store.post_message(self.session_id, ModelMessage(role="assistant", content=response_message))
        return {"res":response_message, "relevant_tools_in_query": json.loads(relevant_tools), "all_session_messages": session_messages}
    
    async def create_new_agent_session(self):
        new_session_id = self.session_store.create_session()
        self.session_id = new_session_id
        return new_session_id