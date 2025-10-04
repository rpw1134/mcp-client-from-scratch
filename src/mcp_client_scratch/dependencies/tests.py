from typing import Optional
from ..utils.initialize_logic import initialize_test_stdio_client
from fastapi import HTTPException

class StdioClientManager:
    """Singleton manager for a testable STDIO client instance."""

    _instance: Optional[object] = None

    @classmethod
    async def get_client(cls) -> object:
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

async def get_stdio_client() -> object:
    """Dependency function to get the STDIO client instance."""
    return await StdioClientManager.get_client()

def reset_stdio_client() -> None:
    """Reset the STDIO client singleton."""
    StdioClientManager.reset()