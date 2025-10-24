import json
from fastapi.openapi.utils import get_openapi
from mcp_client_scratch.main import app

def generate_openapi_schema():
    """Create OpenAPI schema for the FastAPI application."""
    # Use app.routes to get all routes with their prefixes intact
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        openapi_version=app.openapi_version,
        description=app.description,
        routes=app.routes,
    )

    with open('openapi.json', 'w') as f:
        json.dump(openapi_schema, f, indent=2)

    return openapi_schema

if __name__ == "__main__":
    generate_openapi_schema()
    
    