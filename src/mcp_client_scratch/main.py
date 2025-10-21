from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
from contextlib import asynccontextmanager
import os
import dotenv
import json
import logging
from pathlib import Path
from .utils.make_llm_request import AI_request
from .utils.constants import SERVER_URLS
from .classes.MCPClient import HTTPMCPClient, STDIOMCPClient
from .classes.SessionStore import SessionStore
from .classes.ClientManager import ClientManager
from .routers import tests, application, servers, clients, tools
from .schemas.requests import MCPRequest, ChatRequest
from .schemas.responses import MCPResponse
from .utils.initialize_logic import initialize_redis_client
from .dependencies.app_state import app_state

# Load environment variables from .env file
dotenv.load_dotenv()
logger = logging.getLogger("uvicorn.error")

@asynccontextmanager
async def lifespan(app: FastAPI):
    await app_state.startup()
    yield
    await app_state.cleanup()

# Create FastAPI app instance
app = FastAPI(title="MCP Client: Scratch", version="1.0.0", lifespan=lifespan)

# Include routers with flat structure
app.include_router(tests.router)
app.include_router(application.router)
app.include_router(servers.router)
app.include_router(clients.router)
app.include_router(tools.router)

@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint returning a welcome message."""
    return {"message": "Welcome to the MCP Client: Scratch API"}

@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "mcp-client"}

