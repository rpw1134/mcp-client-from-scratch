from pydantic import BaseModel

class ModelMessage(BaseModel):
    role: str
    content: str