from typing import Optional
from pydantic import BaseModel

class ChatRequest(BaseModel):
    """Request model for chat messages."""
    message: str

class MCPRequest(BaseModel):
    """Request model for MCP server requests."""

    server_url: str
    method: str
    params: dict
    timeout: Optional[int] = 30