import json
import httpx
from httpx_sse import aconnect_sse

async def parse_sse(response):
    print(f"POSTing JSON-RPC request and listening for SSE stream...")
    async for line in response.aiter_lines():
        if line.strip() == "":
            continue
        print("RAW LINE:", line)
        if line.startswith("data:"):
            data = line[len("data:"):].strip()
            print("DATA:", data)
            try:
                message = json.loads(data)
                if "jsonrpc" in message and "id" in message:
                    return message
                else:
                    print("Received non-JSON-RPC message:", message)
            except json.JSONDecodeError:
                print("Received non-JSON data:", data)
                continue
    return json.loads("{error: 'No valid JSON-RPC message received'}")
    


async def init_connection(url: str) -> dict:
    payload = {
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
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"
    }
    
    async with httpx.AsyncClient(headers=headers) as client:
        
        try:
            async with client.stream("POST", url, json=payload) as response:
                headers = response.headers
                content_type = headers.get("Content-Type", "")
                message = {}
                print("Response Content-Type:", content_type)
                match content_type:
                    case "text/event-stream":
                        print("SSE stream detected. Parsing...")
                        message = await parse_sse(response)
                        return message
                    case "application/json":
                        print("JSON response detected. Parsing...")
                        json_response = await response.json()
                        return json_response
                    case _:
                        return {"error": f"Unexpected Content-Type: {content_type}"}
        
                    
                
            # If the loop finishes without returning, the stream closed unexpectedly.
            return {"error": "SSE stream closed before a valid JSON-RPC message was received."}

        except httpx.RequestError as e:
            return {"error": f"Request Error: {e}"}
        except Exception as e:
            return {"error": f"Unexpected error: {e}"}

