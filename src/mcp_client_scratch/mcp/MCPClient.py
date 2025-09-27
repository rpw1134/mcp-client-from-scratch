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
    
    def health_check(self) -> dict:
        return {"status": "healthy", "service": "mcp-client"}
        
    
    
    
class STDIOMCPClient(BaseMCPClient):
    
    def __init__(self, command:str, args:list[str], wkdir: str = "./"):
        self.command = command
        self.args = args
        self.wkdir = wkdir
    
    async def _sub_process(self):
        full_command = [self.command] + self.args
        print(full_command)
        print(self.wkdir)
        try:
            process = await asyncio.create_subprocess_exec(
                *full_command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.wkdir
            )
            self.process = process
        
            if not self.process.stderr:
                raise RuntimeError("Subprocess stderr not available.")
            if not self.process.stdout:
                raise RuntimeError("Subprocess stdout not available.")
            
            while True:
                try:
                    err = await asyncio.wait_for(self.process.stderr.readline(), timeout=5.0)
                except TimeoutError:
                    print("done startup output")
                    break
            while True:
                try:
                    out = await asyncio.wait_for(self.process.stdout.readline(), timeout=5.0)
                except TimeoutError:
                    print("done startup errors")
                    break
                
            print("Subprocess started with PID:", process.pid)
            return process
        except Exception as e:
            raise RuntimeError(f"Failed to start subprocess: {e}")
    
    async def _kill_process(self):
        if self.process:
            self.process.terminate()
            await self.process.wait()
    
    async def initialize_connection(self) -> dict:
        try:
            await self._sub_process()
            if not self.process or not self.process.stdin:
                raise RuntimeError("Subprocess not initialized or stdin not available.")
            if not self.process.stdout:
                raise RuntimeError("Subprocess stdout not available.")
            
            message = json.dumps(INIT_PAYLOAD) + "\n"
            self.process.stdin.write(message.encode())
            
            await self.process.stdin.drain()
            
            if self.process.stdin.is_closing():
                raise RuntimeError("Subprocess stdin is closed.")

            print("Initialization message sent, awaiting response...")
            

            response_line = await asyncio.wait_for(self.process.stdout.readline(), timeout=5.0)   
            response = ""
            if response_line:
                response = response_line.decode().strip()
                print("Received response:", response)  
                
            print('end')
            return json.loads(response)
        
        except Exception as e:
            return {"error": f"Failed to send initialization message: {e}"}
    
    
    
    


class HTTPMCPClient(BaseMCPClient):
    
    def __init__(self, url: str):
        self.url = url
    
    async def initialize_connection(self) -> dict:
        async with httpx.AsyncClient(headers=INIT_HEADERS) as client:
            try:
                async with client.stream("POST", self.url, json=INIT_PAYLOAD) as response:
                    headers = response.headers
                    content_type = headers.get("Content-Type", "")
                    message = {}
                    
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
        