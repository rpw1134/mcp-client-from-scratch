import redis
from uuid import uuid4
from ..schemas.session import ModelMessage
from typing import List

class SessionStore():
    """Session store class to manage sessions using Redis."""
    
    def __init__(self, redis_client: redis.Redis):
        """Initialize the Redis connection."""
        self.redis_client = redis_client
    
    def create_session(self)-> str:
        """Create a new session."""
        session_id = uuid4().hex
        # Create an empty list for the session with expiration
        self.redis_client.lpush(session_id, "")  # Push empty placeholder
        self.redis_client.lpop(session_id)  # Remove it (key now exists but empty)
        self.redis_client.expire(session_id, 3600)
        return session_id
    
    def get_session_messages(self, session_id: str) -> List[ModelMessage]:
        """Retrieve all messages for a given session ID."""
        raw_messages: list[bytes] = self.redis_client.lrange(session_id, 0, -1)  # type: ignore
        return [ModelMessage.model_validate_json(msg) for msg in raw_messages]
    
    def post_message(self, session_id: str, message: ModelMessage) -> None:
        """Add a message to the session's message list."""
        self.redis_client.rpush(session_id, message.model_dump_json())
        self.redis_client.expire(session_id, 3600)  # Reset expiration on each message addition
    
    def clear_session(self, session_id: str) -> None:
        """Clear all messages for a given session ID."""
        self.redis_client.delete(session_id)
        
    def close(self) -> None:
        """Close the Redis connection."""
        self.redis_client.close()
    
    
    
    