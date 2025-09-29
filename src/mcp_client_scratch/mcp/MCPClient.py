from ..utils.enums import TransportType
from ..utils.constants import INIT_HEADERS, INIT_PAYLOAD, TOOLS_PAYLOAD
from ..utils.parse_responses import parse_sse
import subprocess
import json
import asyncio
import httpx
from abc import ABC, abstractmethod

class BaseMCPClient(ABC):
    
    def __init__(self):
        self.current_id : int = 1
        self.waiting_requests : dict[int, asyncio.Future] = {}
    
    @abstractmethod
    async def initialize_connection(self) -> dict:
        pass
    
    @abstractmethod
    async def send_request(self, payload: dict) -> dict:
        pass
    
    @abstractmethod
    async def get_tools(self) -> dict:
        pass
    
    @abstractmethod
    async def _continuous_read(self):
        pass
    
    def health_check(self) -> dict:
        return {"status": "healthy", "service": "mcp-client"}
        
    
    
    
class STDIOMCPClient(BaseMCPClient):
    
    def __init__(self, command:str, args:list[str], wkdir: str = "./"):
        self.command = command
        self.args = args
        self.wkdir = wkdir
        super().__init__()
    
    async def _sub_process(self):
        full_command = [self.command] + self.args

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
                    await asyncio.wait_for(self.process.stderr.readline(), timeout=0.2)
                except TimeoutError:
                    break
            while True:
                try:
                    await asyncio.wait_for(self.process.stdout.readline(), timeout=0.2)
                except TimeoutError:
                    break
                
            print("Subprocess started with PID:", process.pid)
            return process
        except Exception as e:
            raise RuntimeError(f"Failed to start subprocess: {e}")
    
    async def _kill_process(self)->int:
        # define return code
        ret_code = -1
        try:
            # if process is available, terminate it
            if self.process:
                self.process.terminate()
                ret_code = await self.process.wait()
                print(f"Subprocess with PID {self.process.pid} terminated with return code {ret_code}.")
            else:
                raise RuntimeError("No subprocess to terminate.")
        # if no process, show
        except RuntimeError as re:
            print(re)
        except Exception as e:
            print(f"Error terminating subprocess: {e}")
            
        # return return code or -1 if error
        return ret_code
    
    async def initialize_connection(self) -> dict:
        try:
            # init the subprocess, check all connections and buffers
            await self._sub_process()
            if not self.process or not self.process.stdin:
                raise RuntimeError("Subprocess not initialized or stdin not available.")
            if not self.process.stdout:
                raise RuntimeError("Subprocess stdout not available.")
            
            # write the init message to stdin and clean buffer
            message = json.dumps(INIT_PAYLOAD) + "\n"
            self.process.stdin.write(message.encode())
            await self.process.stdin.drain()
            
            # ensure stdin is open
            if self.process.stdin.is_closing():
                raise RuntimeError("Subprocess stdin is closed.")

            # receive the init response, send acknowledgement notification, start continuous read loop
            response_line = await asyncio.wait_for(self.process.stdout.readline(), timeout=2.0)   
            response = ""
            if response_line:
                response = response_line.decode().strip()
                print("Received response:", response)  
            await self.send_notification("notifications/initialized", {"status": "ready"})
            asyncio.create_task(self._continuous_read())
            self.current_id+=1

            # return the init response for debug purposes
            return json.loads(response)
        
        # any exceptions caught and returned as error message, process killed
        # TODO: exponential backoff and retry logic
        except Exception as e:
            await self._kill_process()
            return {"error": f"Failed to send initialization message: {e}"}
        
    async def send_request(self, payload: dict) -> dict:
        try:
            # check process status
            if not self.process or not self.process.stdin:
                raise RuntimeError("Subprocess not initialized or stdin not available.")
            
            # get the current id and set id of the payload, increment id in synchronous part of func, dump into json, write, drain buffer
            curr_id = self.current_id
            self.current_id += 1
            request_payload = payload.copy()
            request_payload["id"] = curr_id
            request = json.dumps(payload) + "\n"
            self.process.stdin.write(request.encode())
            await self.process.stdin.drain()
            
            # ensure stdin is still open
            if self.process.stdin.is_closing():
                raise RuntimeError("Subprocess stdin is closed.")
            
            # if all is well, create a future to receive the response and wait for it with timeout
            self.waiting_requests[curr_id] = asyncio.Future()
            response = await asyncio.wait_for(self.waiting_requests[curr_id], timeout = 10.0)
            
            # remove request from memory
            del self.waiting_requests[curr_id]
        
        # TODO: reopen stdin in case of thrown runtime error
        except RuntimeError as e:
            await self._kill_process()
            response = {"error": f"Runtime error: {e}"}
        except TimeoutError as e:
            response = {"error": "The request timed out. Try again. Error: {e}"}
        except Exception as e:
            response = {"error": f"Failed to send request: {e}"}
        
        return response
    
    
    async def send_notification(self, method, params=None):
      notification = {
          "jsonrpc": "2.0",
          "method": method,
          "params": params or {}
      }
      try:
        if not self.process or not self.process.stdin:
              raise RuntimeError("Subprocess not initialized or stdin not available.")
        message = json.dumps(notification) + "\n"
        self.process.stdin.write(message.encode())
        await self.process.stdin.drain()
      except Exception as e:
          print(f"Failed to send notification: {e}")
          return

    
            
        
    async def get_tools(self) -> dict:
        response = await self.send_request(TOOLS_PAYLOAD)
        return response

    async def _continuous_read(self):
        if not self.process or not self.process.stdout:
            raise RuntimeError("Subprocess not initialized or stdout not available.")
        try:
            while True:
                response_line = await self.process.stdout.readline()
                if not response_line:
                    raise RuntimeError("Subprocess stdout closed unexpectedly.")
                response = response_line.decode().strip()
                print("Received response:", response)
                return_response = json.loads(response)
                if "id" in return_response and return_response["id"] in self.waiting_requests:
                    print("Response Received for ID:", return_response["id"])
                    future = self.waiting_requests[return_response["id"]]
                    if not future.done():
                        future.set_result(return_response)
                else:
                    print("Notification Received:", response)
                
        except json.JSONDecodeError as e:
            print(f"Invalid JSON received")
            
        except Exception as e:
            print(f"Error in continuous read: {e}")
            await self._kill_process()
    
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
    
    async def get_tools(self) -> dict:
        return {}

    async def _continuous_read(self):
        pass
        