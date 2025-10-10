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
from .routers import tests, application
from .schemas.requests import MCPRequest, ChatRequest
from .schemas.responses import MCPResponse
from .utils.initialize_logic import initialize_redis_client
from .dependencies.connections import app_state

# Load environment variables from .env file
dotenv.load_dotenv()
logger = logging.getLogger("uvicorn.error")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize singletons
    app_state.redis_client = initialize_redis_client()
    app_state.session_store = SessionStore(redis_client=app_state.redis_client)

    # Load server config from file and initialize client manager
    config_path = Path(__file__).parent / "server_config.json"
    with open(config_path) as f:
        config_data = json.load(f)
    app_state.client_manager = ClientManager(config_data, app_state.redis_client)

    logger.info(f"✓ Redis connected: {app_state.redis_client.ping()}")
    logger.info("✓ SessionStore initialized")
    logger.info("✓ ClientManager loaded")

    # Initialize all clients eagerly
    await app_state.client_manager.initialize_clients()

    # Log client status
    running = app_state.client_manager.get_running_clients()
    failed = app_state.client_manager.get_failed_clients()
    logger.info(f"✓ Clients running: {list(running.keys())}")
    if failed:
        logger.warning(f"✗ Clients failed: {list(failed.keys())}")
    yield

    # Shutdown: Cleanup
    if app_state.client_manager:
        await app_state.client_manager.cleanup_clients()
    if app_state.redis_client:
        app_state.redis_client.flushdb()  # For testing
        app_state.redis_client.close()
    app_state.redis_client = None
    app_state.session_store = None
    app_state.client_manager = None
    logger.info("✓ Cleanup complete")

# Create FastAPI app instance
app = FastAPI(title="MCP Client: Scratch", version="1.0.0", lifespan=lifespan)
app.include_router(tests.router)
app.include_router(application.router)

@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint returning a welcome message."""
    return {"message": "Welcome to the MCP Client: Scratch API"}

@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "mcp-client"}

