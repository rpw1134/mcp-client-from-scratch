from typing import Optional
from pydantic import BaseModel

class ChatRequest(BaseModel):
    message: str
    
class MCPRequest(BaseModel):
    server_url: str
    method: str
    params: dict
    timeout: Optional[int] = 30