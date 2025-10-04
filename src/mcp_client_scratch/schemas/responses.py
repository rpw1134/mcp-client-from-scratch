from typing import Optional
from pydantic import BaseModel

class MCPResponse(BaseModel):
    """Response model for MCP server responses."""

    success: bool
    data: dict
    error: Optional[str] = None