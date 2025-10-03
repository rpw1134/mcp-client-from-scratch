from typing import Optional
from pydantic import BaseModel

class MCPResponse(BaseModel):
    success: bool
    data: dict
    error: Optional[str] = None