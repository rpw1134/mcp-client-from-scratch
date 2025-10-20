from ..classes.MCPClient import STDIOMCPClient, HTTPMCPClient
from .constants import SERVER_URLS
import redis


async def initialize_stdio_client(name, command: str, args: list[str], wkdir: str = "./") -> STDIOMCPClient:
    """Initialize a STDIO MCP client.

    Args:
        command: Command to execute
        args: Arguments for the command
        wkdir: Working directory for the subprocess

    Returns:
        Initialized STDIO MCP client
    """
    stdio_client = STDIOMCPClient(name, command, args, wkdir)
    await stdio_client.initialize_connection()
    return stdio_client

async def initialize_test_stdio_client() -> STDIOMCPClient:
    """Initialize the test STDIO client using the local everything server configuration.

    Returns:
        Initialized test STDIO MCP client
    """
    stdio_test_args = SERVER_URLS['local_everything_server_stdio']
    test_stdio_client = await initialize_stdio_client("everything", stdio_test_args[0], stdio_test_args[1], stdio_test_args[2] if len(stdio_test_args) > 2 else "./")
    return test_stdio_client

async def initialize_http_client(name: str, url: str) -> HTTPMCPClient:
    """Initialize an HTTP MCP client.

    Args:
        name: Name identifier for the client
        url: HTTP URL of the MCP server

    Returns:
        Initialized HTTP MCP client
    """
    http_client = HTTPMCPClient(name, url)
    await http_client.initialize_connection()
    return http_client

async def initialize_test_http_client() -> HTTPMCPClient:
    """Initialize the test HTTP client using the local everything server configuration.

    Returns:
        Initialized test HTTP MCP client
    """
    http_url = SERVER_URLS['local_everything_server_http']
    test_http_client = await initialize_http_client("everything_http", http_url)
    return test_http_client

def initialize_redis_client() -> redis.Redis:
    """Initialize a Redis client.

    Returns:
        Initialized Redis client with decode_responses=True for JSON compatibility
    """
    pool = redis.ConnectionPool(host='localhost', port=6379, db=0, decode_responses=True)
    redis_client = redis.Redis(connection_pool=pool, decode_responses=True)
    try:
        redis_client.ping()
    except redis.ConnectionError as e:
        raise RuntimeError(f"Failed to connect to Redis: {str(e)}")
    return redis_client