from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
import os
import dotenv
from .utils.make_request import AI_request

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
    return {"message": "MCP Client API is running!"}

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