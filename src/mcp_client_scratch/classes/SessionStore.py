import redis
from uuid import uuid4
from ..schemas.session import ModelMessage
from typing import List

class SessionStore():
    """Session store class to manage sessions using Redis."""
    
    def __init__(self):
        pool = redis.ConnectionPool(host='localhost', port=6379, db=0, decode_responses=False)
        self.redis_client = redis.Redis(connection_pool=pool, decode_responses=False)
    
    def create_session(self)-> str:
        """Create a new session with the given session ID."""
        session_id = uuid4().hex
        self.redis_client.expire(session_id, 3600)
        return session_id
    
    def get_session_messages(self, session_id: str) -> List[ModelMessage]:
        raw_messages: list[bytes] = self.redis_client.lrange(session_id, 0, -1)  # type: ignore
        return [ModelMessage.model_validate_json(msg) for msg in raw_messages]
    
    def post_message(self, session_id: str, message: ModelMessage) -> None:
        self.redis_client.rpush(session_id, message.model_dump_json())
        self.redis_client.expire(session_id, 3600)  # Reset expiration on each message addition
    
    def clear_session(self, session_id: str) -> None:
        self.redis_client.delete(session_id)
        
    def close(self) -> None:
        self.redis_client.close()
    
    
    
    