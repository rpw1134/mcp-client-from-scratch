from enum import Enum

class TransportType(Enum):
    """Enum for MCP transport types."""

    STDIO = "stdio"
    HTTP = "http"
    