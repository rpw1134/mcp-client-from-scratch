"""Application state and dependency injection for shared resources."""

from typing import Optional
from redis import Redis
from ..classes.SessionStore import SessionStore
from ..classes.ClientManager import ClientManager


class AppState:
    """Global application state manager for singleton resources."""

    redis_client: Optional[Redis] = None
    session_store: Optional[SessionStore] = None
    client_manager: Optional[ClientManager] = None


# Module-level singleton instance
app_state = AppState()


async def get_redis_client() -> Redis:
    """Dependency to get Redis client.

    Returns:
        Redis client instance

    Raises:
        RuntimeError: If Redis client not initialized
    """
    if app_state.redis_client is None:
        raise RuntimeError("Redis client not initialized. Ensure lifespan startup completed.")
    return app_state.redis_client


async def get_session_store() -> SessionStore:
    """Dependency to get SessionStore singleton.

    Returns:
        SessionStore instance

    Raises:
        RuntimeError: If SessionStore not initialized
    """
    if app_state.session_store is None:
        raise RuntimeError("SessionStore not initialized. Ensure lifespan startup completed.")
    return app_state.session_store


async def get_client_manager() -> ClientManager:
    """Dependency to get ClientManager singleton.

    Returns:
        ClientManager instance

    Raises:
        RuntimeError: If ClientManager not initialized
    """
    if app_state.client_manager is None:
        raise RuntimeError("ClientManager not initialized. Ensure lifespan startup completed.")
    return app_state.client_manager
