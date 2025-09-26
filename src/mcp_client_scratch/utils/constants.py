SYSTEM_PROMPT = "You are the first stage of a multi-stage AI system. Your job is to take in a users request, reference the available tools, and decide which tool is best to use given the request. Your response will contain only the title of the tool that is best to use. If no tool is appropriate, respond with 'None'. If the task can be answered without a tool, respond 'Chat'."

SERVER_URLS = {'example_server': 'https://echo.mcp.inevitable.fyi/mcp', 'local_server': 'http://localhost:3001/mcp'}

INIT_PAYLOAD = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "roots": {"listChanged": True},
                "sampling": {}
            },
            "clientInfo": {
                "name": "ExampleClient",
                "version": "1.0.0"
            }
        }
    }

INIT_HEADERS = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream, text/html"
    }