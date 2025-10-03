from ..utils.constants import INIT_HEADERS, INIT_PAYLOAD, TOOLS_PAYLOAD, BASE_TOOLS
from ..utils.parse_responses import parse_sse
import json
import asyncio
import httpx
from abc import ABC, abstractmethod
from .Process import Process

class BaseMCPClient(ABC):
    
    def __init__(self):
        self.current_id : int = 1
        self.waiting_requests : dict[int, asyncio.Future] = {}
        self.tools = {**BASE_TOOLS}
    
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
    
    def _set_tools(self, tools: dict):
        for tool in tools:
            self.tools[tool["name"]] = tool
            self.tools[tool["name"]]["source"] = "server"
        
        
    
class STDIOMCPClient(BaseMCPClient):
    
    def __init__(self, command:str, args:list[str], wkdir: str = "./"):
        self.command = command
        self.args = args
        self.wkdir = wkdir
        super().__init__()
    
    async def _sub_process(self):
        # parse full server start command
        full_command = [self.command] + self.args

        try:
            self.process = Process(command=full_command, wkdir=self.wkdir)
            await self.process.start()
            
            # clear initial buffers
            await self.process.read_startup_notifications()
                
            print("Subprocess started with PID:", self.process.pid)
        
        except Exception as e:
            raise RuntimeError(f"Failed to start subprocess: {e}")
    
    async def _kill_process(self)->int:
        # define return code
        ret = -1
        try:
            ret = await self.process.terminate()
        
        # no process?
        except RuntimeError as re:
            print(re)
        # error terminating
        except Exception as e:
            print(f"Error terminating subprocess: {e}")
            
        # return return code or -1 if error
        return ret
    
    async def initialize_connection(self) -> dict:
        try:
            # init the subprocess, check all connections and buffers
            await self._sub_process()
            if not self.process or not self.process.is_running():
                raise RuntimeError("Subprocess not initialized or not running.")

            # write the init message to stdin using Process method
            message = json.dumps(INIT_PAYLOAD)
            await self.process.write_stdin(message)

            # receive the init response using Process method
            response = await self.process.read_stdout(timeout=2.0)
            if response:
                print("Received response:", response)
            await self.send_notification("notifications/initialized", {"status": "ready"})
            asyncio.create_task(self._continuous_read())
            self.current_id+=1

            # return the init response for debug purposes
            return json.loads(response) if response else {}
        
        # any exceptions caught and returned as error message, process killed
        # TODO: exponential backoff and retry logic
        except Exception as e:
            await self._kill_process()
            return {"error": f"Failed to send initialization message: {e}"}
        
    async def send_request(self, payload: dict) -> dict:
        try:
            # check process status
            if not self.process or not self.process.is_running():
                raise RuntimeError("Subprocess not initialized or not running.")

            # get the current id and set id of the payload, increment id in synchronous part of func
            curr_id = self.current_id
            self.current_id += 1
            request_payload = payload.copy()
            request_payload["id"] = curr_id
            request = json.dumps(request_payload)
            await self.process.write_stdin(request)

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
    
    
    async def send_notification(self, method: str, params: dict={}):
        # define notification payload
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }

        try:
            # check process status, write notification using Process method
            if not self.process or not self.process.is_running():
                    raise RuntimeError("Subprocess not initialized or not running.")
            message = json.dumps(notification)
            await self.process.write_stdin(message)

        except Exception as e:
            print(f"Failed to send notification: {e}. Please try again.")

    
    async def get_tools(self) -> dict:
        # make request for a given set of tools
        response = await self.send_request(TOOLS_PAYLOAD)
        if "result" in response and "tools" in response["result"]:
            self._set_tools(response["result"]["tools"])
        else:
            print("No tools found in response or error occurred:", response)
        return self.tools

    async def _continuous_read(self):
        # check validity of process
        if not self.process or not self.process.is_running():
            raise RuntimeError("Subprocess not initialized or not running.")
        try:
            # set continuous read loop
            while True:
                # read response using Process method (non-blocking)
                response = await self.process.read_stdout_nowait()

                # if no response, subprocess has closed stdout, raise error
                if not response:
                    raise RuntimeError("Subprocess stdout closed unexpectedly.")

                # parse response into a dict
                return_response = json.loads(response)

                # if a response, resolve associated request future
                if "id" in return_response and return_response["id"] in self.waiting_requests:
                    print("Response Received for ID:", return_response["id"])
                    future = self.waiting_requests[return_response["id"]]
                    if not future.done():
                        future.set_result(return_response)

                # TODO: future notification handling
                else:
                    print("Notification Received:", response)
        
        #TODO: exponential backoff and retry logic
        except RuntimeError as re:
            print(f"Runtime error in continuous read: {re}")
            await self._kill_process()
        except json.JSONDecodeError as e:
            print(f"Invalid JSON received")
        except Exception as e:
            print(f"Error in continuous read: {e}")
            await self._kill_process()
    
class HTTPMCPClient(BaseMCPClient):
    
    def __init__(self, url: str):
        self.url = url
    
    async def initialize_connection(self) -> dict:
        # initialize http client
        # TODO: pooling?
        async with httpx.AsyncClient(headers=INIT_HEADERS) as client:
            try:
                async with client.stream("POST", self.url, json=INIT_PAYLOAD) as response:
                    # parse headers and content type from response
                    headers = response.headers
                    content_type = headers.get("Content-Type", "")
                    message = {}
                    
                    match content_type:
                        # if sse, parse as sse
                        case "text/event-stream":
                            print("SSE stream detected. Parsing...")
                            message = await parse_sse(response)
                            return message
                        # if json, parse as json
                        case "application/json":
                            print("JSON response detected. Parsing...")
                            json_response = await response.json()
                            return json_response
                        # TODO: handle streamed json
                        case _:
                            return {"error": f"Unexpected Content-Type: {content_type}"}
        
                return {"error": "Stream closed before a valid JSON-RPC message was received."}

            except httpx.RequestError as e:
                return {"error": f"Request Error: {e}"}
            except Exception as e:
                return {"error": f"Unexpected error: {e}"}
    
    async def get_tools(self) -> dict:
        return {}

    async def _continuous_read(self):
        pass
        