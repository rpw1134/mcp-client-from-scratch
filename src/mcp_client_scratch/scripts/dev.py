import uvicorn
from mcp_client_scratch.main import app

def dev() -> None:
    """Development server entry point."""
    uvicorn.run(
        "mcp_client_scratch.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True
    )

if __name__ == "__main__":
    dev()