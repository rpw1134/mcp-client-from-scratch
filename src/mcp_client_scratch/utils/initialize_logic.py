from ..classes.MCPClient import STDIOMCPClient
from .constants import SERVER_URLS


async def initialize_stdio_client(command: str, args: list[str], wkdir: str = "./") -> STDIOMCPClient:
    """Initialize a STDIO MCP client.

    Args:
        command: Command to execute
        args: Arguments for the command
        wkdir: Working directory for the subprocess

    Returns:
        Initialized STDIO MCP client
    """
    stdio_client = STDIOMCPClient(command, args, wkdir)
    await stdio_client.initialize_connection()
    return stdio_client

async def initialize_test_stdio_client() -> STDIOMCPClient:
    """Initialize the test STDIO client using the local everything server configuration.

    Returns:
        Initialized test STDIO MCP client
    """
    stdio_test_args = SERVER_URLS['local_everything_server_stdio']
    test_stdio_client = await initialize_stdio_client(stdio_test_args[0], stdio_test_args[1], stdio_test_args[2] if len(stdio_test_args) > 2 else "./")
    return test_stdio_client