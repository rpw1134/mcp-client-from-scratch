"""Application state and dependency injection for shared resources."""

from typing import Optional
from redis import Redis
from ..classes.SessionStore import SessionStore
from ..classes.ServerConfig import ServerConfig


class AppState:
    """Global application state manager for singleton resources."""

    redis_client: Optional[Redis] = None
    session_store: Optional[SessionStore] = None
    server_config: Optional[ServerConfig] = None


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


async def get_server_config() -> ServerConfig:
    """Dependency to get ServerConfig singleton.

    Returns:
        ServerConfig instance

    Raises:
        RuntimeError: If ServerConfig not initialized
    """
    if app_state.server_config is None:
        raise RuntimeError("ServerConfig not initialized. Ensure lifespan startup completed.")
    return app_state.server_config
