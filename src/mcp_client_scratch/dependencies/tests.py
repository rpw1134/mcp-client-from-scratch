from typing import Optional
from ..utils.initialize_logic import initialize_test_stdio_client
from fastapi import HTTPException

class StdioClientManager:
    _instance: Optional[object] = None
    
    @classmethod
    async def get_client(cls):
        if cls._instance is None:
            try:
                cls._instance = await initialize_test_stdio_client()
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to initialize stdio client: {str(e)}")
        return cls._instance
    
    @classmethod
    def reset(cls):
        cls._instance = None

async def get_stdio_client():
    return await StdioClientManager.get_client()

def reset_stdio_client():
    StdioClientManager.reset()