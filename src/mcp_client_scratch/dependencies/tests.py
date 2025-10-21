from typing import Optional
from ..utils.initialize_logic import initialize_test_stdio_client, initialize_test_http_client
from fastapi import HTTPException
from ..classes.SessionStore import SessionStore
from typing import Generator
from ..utils.initialize_logic import initialize_redis_client
from ..classes.MCPClient import HTTPMCPClient, STDIOMCPClient
import logging

logger = logging.getLogger("uvicorn.error")
class StdioClientManager:
    """Singleton manager for a testable STDIO client instance."""

    _instance: Optional[STDIOMCPClient] = None

    @classmethod
    async def get_client(cls) -> STDIOMCPClient:
        """Get or create the STDIO client instance.

        Returns:
            The STDIO client instance

        Raises:
            HTTPException: If client initialization fails
        """
        if cls._instance is None:
            try:
                cls._instance = await initialize_test_stdio_client()
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to initialize stdio client: {str(e)}")
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the STDIO client instance."""
        cls._instance = None

class HttpClientManager:
    """Singleton manager for a testable HTTP client instance."""

    _instance: Optional[HTTPMCPClient] = None

    @classmethod
    async def get_client(cls) -> HTTPMCPClient:
        """Get or create the HTTP client instance.

        Returns:
            The HTTP client instance

        Raises:
            HTTPException: If client initialization fails
        """
        if cls._instance is None:
            try:
                cls._instance = await initialize_test_http_client()
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to initialize HTTP client: {str(e)}")
        return cls._instance

    @classmethod
    async def reset(cls) -> None:
        """Reset the HTTP client instance and clean up resources."""
        if cls._instance is not None:
            try:
                # Call close method if available
                if hasattr(cls._instance, 'close_connection'):
                    await cls._instance.close_connection()
            except Exception as e:
                logger.error(f"Error closing HTTP client: {e}")
        cls._instance = None

async def get_stdio_client() -> STDIOMCPClient:
    """Dependency function to get the STDIO client instance."""
    return await StdioClientManager.get_client()

def reset_stdio_client() -> None:
    """Reset the STDIO client singleton."""
    StdioClientManager.reset()

async def get_http_client() -> HTTPMCPClient:
    """Dependency function to get the HTTP client instance."""
    return await HttpClientManager.get_client()

async def reset_http_client() -> None:
    """Reset the HTTP client singleton."""
    await HttpClientManager.reset()
    
def get_session_store() -> Generator[SessionStore, None, None]:
    """Dependency function to get the session store instance."""
    session_store: Optional[SessionStore] = None
    try:
        redis_client = initialize_redis_client()
        session_store = SessionStore(redis_client=redis_client)
        yield session_store
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to connect to Redis: {str(e)}")
    finally:
        if session_store:
            session_store.close()