from fastapi import APIRouter, Depends, Query
from ..dependencies.connections import get_server_config, get_session_store, get_redis_client

router = APIRouter(prefix="/app", tags=["app"])
