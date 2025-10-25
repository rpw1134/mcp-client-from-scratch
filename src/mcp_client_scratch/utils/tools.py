import hashlib
import json

def hash_tool(tool: dict[str, dict]) -> str:
    """Generate a hash for a given tool."""
    tools_json = json.dumps(tool, sort_keys=True)
    return hashlib.sha256(tools_json.encode('utf-8')).hexdigest()