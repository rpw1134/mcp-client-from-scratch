from ..schemas.session import ModelMessage
from ..schemas.requests import ChatRequest
from ..classes.SessionStore import SessionStore
from ..classes.VectorStore import VectorStore
from ..classes.OpenAIClient import OpenAIClient
from ..classes.ClientManager import ClientManager
from ..utils.parse_responses import format_tool_response
import json
from openai.types.chat import ChatCompletionMessageParam
from ..utils.constants import SYSTEM_PROMPT_BASE, BASE_TOOLS
from typing import cast
import uuid
from collections import deque

class Agent:
    
    # An agent shall be responsible for keeping track of: session context length, current requests that need more information aka tools that are waiting on information, current session. 
    # An agent shall be responsible for summarizing session context if exceeds a context length, removing tools from pending requests after they are fulfilled (or if the requests exceed the ttl)
    
    def __init__(self, session_store, vector_store, openai_client, client_manager):
        self.session_store: SessionStore = session_store
        self.vector_store: VectorStore = vector_store
        self.openai_client: OpenAIClient = openai_client
        self.client_manager: ClientManager = client_manager
        self.session_id = uuid.uuid4().hex
        self.queue = deque()
        self.pending_tools = {}
        self.ttl = 5
        self.time = 0
        
    
    async def process_request(self, user_message: str):
        # Before processing, clean up expired pending tools
        self._before()
        
        # store user message in session
        new_message = ModelMessage(role="user", content=user_message)
        self.session_store.post_message(self.session_id, new_message)
        
        # get relevant context for the request
        session_messages = self.session_store.get_session_messages(self.session_id)
        relevant_tools = await self.vector_store.query_similar_tools(user_message,5)
        
        # cleanup for request
        for tool in relevant_tools:
            del tool["hash"]
            
        # convert to json string for prompt
        relevant_tools = json.dumps(relevant_tools)
        response_message = await self.openai_client.tool_selection_request(system_prompt=f"{SYSTEM_PROMPT_BASE} {BASE_TOOLS} {self.pending_tools} {relevant_tools}", messages = [cast(ChatCompletionMessageParam, message) for message in session_messages], model='gpt-4o')
        
        # check response for tool calls that need to be added to pending tools
        self._process_tool_response(response_message)
        
        # add message to session
        self.session_store.post_message(self.session_id, ModelMessage(role="assistant", content=response_message))
        return {"res":response_message}
    
    async def call_tool(self, agent_response: str):
        try:
            agent_response_json: dict = json.loads(agent_response)
            call_source = agent_response_json.get("source","")
            tool = agent_response_json.get("params",{})
            if call_source == "native":
                return "Native tool calls not yet implemented."
            elif call_source == "":
                raise RuntimeError("No source specified in tool call.")
            client = self.client_manager.get_client(call_source)
            if not client:
                raise RuntimeError(f"Client {call_source} not found.")
            if not tool:
                raise RuntimeError(f"No tool specified in tool call.")
            response = await client.send_request(tool, function="execute")
            return response
        except RuntimeError as e:
            return f"I encountered an error while processing your request. Please try again! Error details: {str(e)}"
        except json.JSONDecodeError:
            return "I encountered an error while processing your request. Please try again!"
    
    def create_new_agent_session(self):
        new_session_id = self.session_store.create_session()
        self.session_id = new_session_id
        return new_session_id
    
    def _process_tool_response(self, tool_response: str):
        """Process the tool response from the agent and update session state accordingly."""
        try:
            # get all possible needed data from tool response
            tool_response_json: dict = json.loads(format_tool_response(tool_response))
            params: dict = tool_response_json.get("params", {})
            
            tool_name = params.get("name", "")
            tool_source = tool_response_json.get("source", "")
            
            tool_to_be_populated: dict = params.get("arguments", {}).get("tool_to_be_populated", {})
            client_name = tool_to_be_populated.get("source", "")
            tool_to_be_populated_name = tool_to_be_populated.get("name", "")
            
            # check if tool is 'info'. If so and if there is a tool to come back to, add to pending tools
            if tool_name == 'info' and len(tool_to_be_populated)>0:
                if not client_name or not tool_to_be_populated_name:
                    return
                client = self.client_manager.get_client(client_name)
                if not client:
                    return
                tool = client.get_tool_by_name(tool_to_be_populated_name)
                if not tool:
                    return
                
                # if so, add to pending tools with ttl
                self.queue.append((tool_to_be_populated_name+":"+client_name, self.time+self.ttl))
                self.pending_tools[tool_to_be_populated_name+":"+client_name] = tool
            
            # else, if tool is not 'info', check if it fulfills a pending tool
            else:
                unique_key = tool_name+":"+tool_source
                if unique_key in self.pending_tools:
                    del self.pending_tools[unique_key]
            return True
        
        except json.JSONDecodeError:
            print("Failed to decode tool response JSON.")
            return False
        
    def _before(self):
        # Increment time and clean up expired pending tools
        # TODO: LRU or other better structure for pending tools
        self.time+=1
        if self.queue and self.queue[0][1]<=self.time:
            expired_tool = self.queue.popleft()
            if expired_tool[0] in self.pending_tools:
                del self.pending_tools[expired_tool[0]]
        print(f"Pending tools: {self.pending_tools.keys()} at time {self.time}")