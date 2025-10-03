from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
import os
import dotenv
from .utils.make_request import AI_request
from .utils.constants import SYSTEM_PROMPT, SERVER_URLS
from .classes.MCPClient import HTTPMCPClient, STDIOMCPClient

# Load environment variables from .env file
dotenv.load_dotenv()

# Create FastAPI app instance
app = FastAPI(title="MCP Client: Scratch", version="1.0.0")

class MCPRequest(BaseModel):
    server_url: str
    method: str
    params: dict
    timeout: Optional[int] = 30

class MCPResponse(BaseModel):
    success: bool
    data: dict
    error: Optional[str] = None

class ChatRequest(BaseModel):
    message: str

@app.get("/")
async def root():
    try:
        # http_client = HTTPMCPClient(url=SERVER_URLS['example_server'])
        # http_response = await http_client.initialize_connection()
        stdio_test_args = SERVER_URLS['local_everything_server_stdio']
        stdio_client = STDIOMCPClient(stdio_test_args[0], stdio_test_args[1], stdio_test_args[2] if len(stdio_test_args) > 2 else "./")
        stdio_response = await stdio_client.initialize_connection()
        stdio_tools = await stdio_client.get_tools()
    except Exception as e:
        stdio_response = {"error": str(e)}
        stdio_tools = {"error": str(e)}
    
    return {"message": "MCP Client API is running!", "stdio_tools": stdio_tools}

@app.post("/test-init-stdio")
async def init_stdio_client():
    try:
        stdio_test_args = SERVER_URLS['local_everything_server_stdio']
        stdio_client = STDIOMCPClient(stdio_test_args[0], stdio_test_args[1], stdio_test_args[2] if len(stdio_test_args) > 2 else "./")
        await stdio_client.initialize_connection()
        await stdio_client.get_tools()
        return stdio_client.tools
    except Exception as e:
        return {"error": str(e)}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "mcp-client"}

@app.get("/chat", response_model=str)
async def chat(request: ChatRequest):
    # Simple echo chat endpoint
    response = AI_request(request.message)  # Call the async AI_request function
    
    return response


# MCP request endpoint
@app.post("/mcp/execute", response_model=MCPResponse)
async def execute_mcp_request(request: MCPRequest):
    try:
        # TODO: Implement actual MCP server communication
        # For now, return mock response
        return MCPResponse(
            success=True,
            data={"result": f"Mock response for {request.method}"}
        )
    except Exception as e:
        return MCPResponse(
            success=False,
            data={},
            error=str(e)
        )