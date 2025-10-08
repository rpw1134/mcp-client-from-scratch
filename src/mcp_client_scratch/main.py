from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
from contextlib import asynccontextmanager
import os
import dotenv
import json
from pathlib import Path
from .utils.make_llm_request import AI_request
from .utils.constants import SERVER_URLS
from .classes.MCPClient import HTTPMCPClient, STDIOMCPClient
from .classes.SessionStore import SessionStore
from .classes.ServerConfig import ServerConfig
from .routers import tests
from .schemas.requests import MCPRequest, ChatRequest
from .schemas.responses import MCPResponse
from .utils.initialize_logic import initialize_redis_client
from .dependencies.connections import app_state

# Load environment variables from .env file
dotenv.load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize singletons
    app_state.redis_client = initialize_redis_client()
    app_state.session_store = SessionStore(redis_client=app_state.redis_client)

    # Load server config from file
    config_path = Path(__file__).parent / "server_config.json"
    with open(config_path) as f:
        config_data = json.load(f)
    app_state.server_config = ServerConfig(config_data, app_state.redis_client)

    print("✓ Redis connected:", app_state.redis_client.ping())
    print("✓ SessionStore initialized")
    print("✓ ServerConfig loaded")

    yield

    # Shutdown: Cleanup
    if app_state.redis_client:
        app_state.redis_client.flushdb()  # For testing
        app_state.redis_client.close()
    app_state.redis_client = None
    app_state.session_store = None
    app_state.server_config = None
    print("✓ Cleanup complete")

# Create FastAPI app instance
app = FastAPI(title="MCP Client: Scratch", version="1.0.0", lifespan=lifespan)
app.include_router(tests.router)

@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint returning a welcome message."""
    return {"message": "Welcome to the MCP Client: Scratch API"}

@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "mcp-client"}

