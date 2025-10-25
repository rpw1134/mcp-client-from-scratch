"""Application state and dependency injection for shared resources."""
import os
from typing import Optional
from redis import Redis
from ..classes.SessionStore import SessionStore
from ..classes.ClientManager import ClientManager
from ..classes.OpenAIClient import OpenAIClient
from ..classes.VectorStore import VectorStore
from ..utils.initialize_logic import initialize_redis_client
import json
import logging
from pathlib import Path

logger = logging.getLogger("uvicorn.error")

class AppState:
    """Global application state manager for singleton resources."""

    redis_client: Optional[Redis] = None
    session_store: Optional[SessionStore] = None
    client_manager: Optional[ClientManager] = None
    openai_client: Optional[OpenAIClient] = None
    vector_store: Optional[VectorStore] = None
    
    async def startup(self) -> None:
        """Startup logic to initialize resources."""
        # connect to redis instance (local)
        self.redis_client = initialize_redis_client()
        if not self.redis_client:
            raise RuntimeError("Failed to initialize Redis client.")
        
        # Initialize the session store with above redis client
        self.session_store = SessionStore(redis_client=self.redis_client)
        
        # Initialize OpenAI for requests and embeddings
        self.openai_client = OpenAIClient()

        # Initialize VectorStore with OpenAI client for embedding persistence
        self.vector_store = VectorStore(self.openai_client, os.getenv("CHROMA_PERSIST_LOCATION", ""))
        
        # Load server config from file and initialize client manager
        config_path = Path(__file__).parent.parent / "server_config.json"
        with open(config_path) as f:
            config_data = json.load(f)
        self.client_manager = ClientManager(config_data, self.redis_client)
         
         # Initialize all clients eagerly
        if not self.client_manager:
            raise RuntimeError("ClientManager not initialized.")
        await self.client_manager.initialize_clients()

        # Log client status
        running = self.client_manager.get_running_clients()
        failed = self.client_manager.get_failed_clients()
        logger.info(f"Clients running: {list(running.keys())}")
        if failed:
            logger.warning(f"Clients failed: {list(failed.keys())}")
        
        
        logger.info(f"Redis connected: {self.redis_client.ping()}")
        logger.info("Session Store initialized")
        logger.info("Client Manager loaded")
        logger.info("OpenAI client initialized")
        logger.info("Vector Store initialized")
    
    async def cleanup(self) -> None:
        """Cleanup logic to release resources."""
        if self.client_manager:
            await self.client_manager.cleanup_clients()
            logger.info("Client Manager cleaned up")
        if self.openai_client:
            await self.openai_client.close()
            logger.info("OpenAI client closed")
        if self.redis_client:
            self.redis_client.flushdb()  # For testing
            self.redis_client.close()
            logger.info("Redis client closed")
        if self.session_store:
            self.session_store.close()
            logger.info("Session Store closed")
        if self.vector_store:
            # Add any necessary cleanup for vector store if needed
            logger.info("Vector Store cleaned up")
        self.redis_client = None
        self.session_store = None
        self.client_manager = None
        self.openai_client = None
        self.vector_store = None
        logger.info("Cleanup complete")


# Module-level singleton instance
app_state = AppState()


def get_redis_client() -> Redis:
    """Dependency to get Redis client.

    Returns:
        Redis client instance

    Raises:
        RuntimeError: If Redis client not initialized
    """
    if app_state.redis_client is None:
        raise RuntimeError("Redis client not initialized. Ensure lifespan startup completed.")
    return app_state.redis_client


def get_session_store() -> SessionStore:
    """Dependency to get SessionStore singleton.

    Returns:
        SessionStore instance

    Raises:
        RuntimeError: If SessionStore not initialized
    """
    if app_state.session_store is None:
        raise RuntimeError("SessionStore not initialized. Ensure lifespan startup completed.")
    return app_state.session_store


def get_client_manager() -> ClientManager:
    """Dependency to get ClientManager singleton.

    Returns:
        ClientManager instance

    Raises:
        RuntimeError: If ClientManager not initialized
    """
    if app_state.client_manager is None:
        raise RuntimeError("ClientManager not initialized. Ensure lifespan startup completed.")
    return app_state.client_manager


def get_openai_client() -> OpenAIClient:
    """Dependency to get OpenAI client instance.

    Lazily initializes the OpenAI client on first request if not already initialized.

    Returns:
        OpenAIClient instance

    Raises:
        ValueError: If OPEN_AI_API_KEY environment variable not set
    """
    if app_state.openai_client is None:
        app_state.openai_client = OpenAIClient()
        logger.info("OpenAI client initialized")
    return app_state.openai_client

def get_vector_store() -> VectorStore:
    """Dependency to get VectorStore singleton.

    Returns:
        VectorStore instance

    Raises:
        RuntimeError: If VectorStore not initialized
    """
    if app_state.vector_store is None:
        raise RuntimeError("VectorStore not initialized. Ensure lifespan startup completed.")
    return app_state.vector_store
