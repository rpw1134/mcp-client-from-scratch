from ..utils.enums import TransportType
from ..utils.constants import INIT_HEADERS, INIT_PAYLOAD
from .init_connection import parse_sse
import subprocess
import json
import asyncio
import httpx
from abc import ABC, abstractmethod

class BaseMCPClient(ABC):
    
    @abstractmethod
    async def initialize_connection(self) -> dict:
        pass
        
    
    
    
# class STDIOMCPClient(BaseMCPClient):
    
#     async def __init__(self, command:str, args:list[str]):
#         self.command = command
#         self.args = args
#         self.process = self._sub_process()
    
#     async def _sub_process(self):
#         full_command = [self.command] + self.args
#         process = await asyncio.create_subprocess_exec(
#             *full_command,
#             stdin=asyncio.subprocess.PIPE,
#             stdout=asyncio.subprocess.PIPE,
#             stderr=asyncio.subprocess.PIPE
#         )
#         return process
    
    


class HTTPMCPClient(BaseMCPClient):
    
    def __init__(self, url: str):
        self.url = url
    
    def health_check(self) -> dict:
        return {"status": "healthy", "service": "mcp-client"}
    async def initialize_connection(self) -> dict:
        print(f"Initializing connection to {self.url}...")
        async with httpx.AsyncClient(headers=INIT_HEADERS) as client:
            try:
                async with client.stream("POST", self.url, json=INIT_PAYLOAD) as response:
                    headers = response.headers
                    content_type = headers.get("Content-Type", "")
                    message = {}
                    print(response)
                    match content_type:
                        case "text/event-stream":
                            print("SSE stream detected. Parsing...")
                            message = await parse_sse(response)
                            return message
                        case "application/json":
                            print("JSON response detected. Parsing...")
                            json_response = await response.json()
                            return json_response
                        case "text/html":
                            print("HTML response detected. Parsing...")
                            return {"error": f"Received HTML response: {response}"}
                        case _:
                            return {"error": f"Unexpected Content-Type: {content_type}"}
        
                return {"error": "SSE stream closed before a valid JSON-RPC message was received."}

            except httpx.RequestError as e:
                return {"error": f"Request Error: {e}"}
            except Exception as e:
                return {"error": f"Unexpected error: {e}"}
        