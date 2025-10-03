from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
import os
import dotenv
from .utils.make_llm_request import AI_request
from .utils.constants import SERVER_URLS
from .classes.MCPClient import HTTPMCPClient, STDIOMCPClient
from .routers import tests
from .schemas.requests import MCPRequest, ChatRequest
from .schemas.responses import MCPResponse

# Load environment variables from .env file
dotenv.load_dotenv()

# Create FastAPI app instance
app = FastAPI(title="MCP Client: Scratch", version="1.0.0")
app.include_router(tests.router)

@app.get("/")
async def root():
    return {"message": "Welcome to the MCP Client: Scratch API"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "mcp-client"}
