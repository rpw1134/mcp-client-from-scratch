from ..utils.constants import INIT_HEADERS, INIT_PAYLOAD, TOOLS_PAYLOAD, BASE_TOOLS
from ..utils.parse_responses import parse_sse
import json
import asyncio
import httpx
from abc import ABC, abstractmethod
from .Process import Process

class BaseMCPClient(ABC):
    """Abstract base class for MCP client implementations."""

    def __init__(self) -> None:
        """Initialize the base MCP client."""
        self.current_id: int = 1
        self.waiting_requests: dict[int, asyncio.Future] = {}
        self.tools: dict = {**BASE_TOOLS}
        self.name = ""
    
    @abstractmethod
    async def initialize_connection(self) -> dict:
        """Initialize connection to the MCP server."""
        pass

    @abstractmethod
    async def send_request(self, payload: dict) -> dict:
        """Send a request to the MCP server."""
        pass

    @abstractmethod
    async def get_tools(self) -> dict:
        """Retrieve available tools from the server."""
        pass

    @abstractmethod
    async def _continuous_read(self) -> None:
        """Continuously read responses from the server."""
        pass
    
    def health_check(self) -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "healthy", "service": "mcp-client"}

    def _set_tools(self, tools: list[dict]) -> None:
        """Store tools retrieved from server.

        Args:
            tools: List of tool definitions from the server
        """
        for tool in tools:
            self.tools[tool["name"]] = tool
            self.tools[tool["name"]]["source"] = "server"
        
        
    
class STDIOMCPClient(BaseMCPClient):
    """MCP client for STDIO-based server communication."""

    def __init__(self, name:str, command: str, args: list[str], wkdir: str = "./", env: dict = {}) -> None:
        """Initialize the STDIO MCP client.

        Args:
            command: Command to execute
            args: Arguments for the command
            wkdir: Working directory for the subprocess
        """
        super().__init__()
        self.command = command
        self.args = args
        self.wkdir = wkdir
        self.env = env
        self.name = name
    
    async def _sub_process(self) -> None:
        """Start the subprocess and clear initial buffers.

        Raises:
            RuntimeError: If subprocess fails to start
        """
        full_command = [self.command] + self.args

        try:
            print(f"Starting subprocess: {' '.join(full_command)}")
            print(f"Working directory: {self.wkdir}")
            print(f"Environment vars: {self.env}")
            self.process = Process(command=full_command, wkdir=self.wkdir, env=self.env)
            await self.process.start()

            await self.process.read_startup_notifications()

            print("Subprocess started with PID:", self.process.pid)

        except Exception as e:
            print(f"ERROR in _sub_process: {e}")
            import traceback
            traceback.print_exc()
            raise RuntimeError(f"Failed to start subprocess: {e}")
    
    async def _kill_process(self) -> int:
        """Terminate the subprocess.

        Returns:
            Return code of the terminated process, or -1 if error
        """
        ret = -1
        try:
            ret = await self.process.terminate()

        except RuntimeError as re:
            print(re)
        except Exception as e:
            print(f"Error terminating subprocess: {e}")

        return ret
    
    async def initialize_connection(self) -> dict:
        """Initialize connection to the STDIO MCP server.

        Returns:
            The initialization response from the server

        Note:
            TODO: Add exponential backoff and retry logic
        """
        try:
            await self._sub_process()
            if not self.process or not self.process.is_running():
                raise RuntimeError("Subprocess not initialized or not running.")

            message = json.dumps(INIT_PAYLOAD)
            await self.process.write_stdin(message)

            response = await self.process.read_stdout(timeout=2.0)
            if response:
                print("Received response:", response)
            await self.send_notification("notifications/initialized", {"status": "ready"})
            asyncio.create_task(self._continuous_read())
            self.current_id += 1

            return json.loads(response) if response else {}

        except Exception as e:
            await self._kill_process()
            return {"error": f"Failed to send initialization message: {e}"}
        
    async def send_request(self, payload: dict) -> dict:
        """Send a JSON-RPC request to the MCP server.

        Args:
            payload: The request payload (without id field)

        Returns:
            The server response

        Note:
            TODO: Reopen stdin in case of thrown runtime error
        """
        try:
            if not self.process or not self.process.is_running():
                raise RuntimeError("Subprocess not initialized or not running.")

            curr_id = self.current_id
            self.current_id += 1
            request_payload = payload.copy()
            request_payload["id"] = curr_id
            request = json.dumps(request_payload)
            await self.process.write_stdin(request)

            self.waiting_requests[curr_id] = asyncio.Future()
            response = await asyncio.wait_for(self.waiting_requests[curr_id], timeout=10.0)

            del self.waiting_requests[curr_id]

        except RuntimeError as e:
            await self._kill_process()
            response = {"error": f"Runtime error: {e}"}
        except TimeoutError as e:
            response = {"error": f"The request timed out. Try again. Error: {e}"}
        except Exception as e:
            response = {"error": f"Failed to send request: {e}"}

        return response
    
    
    async def send_notification(self, method: str, params: dict = {}) -> None:
        """Send a JSON-RPC notification to the MCP server.

        Args:
            method: The notification method
            params: The notification parameters
        """
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }

        try:
            if not self.process or not self.process.is_running():
                raise RuntimeError("Subprocess not initialized or not running.")
            message = json.dumps(notification)
            await self.process.write_stdin(message)

        except Exception as e:
            print(f"Failed to send notification: {e}. Please try again.")

    
    async def get_tools(self) -> dict:
        """Retrieve and store available tools from the MCP server.

        Returns:
            Dictionary of available tools
        """
        response = await self.send_request(TOOLS_PAYLOAD)
        if "result" in response and "tools" in response["result"]:
            self._set_tools(response["result"]["tools"])
        else:
            print("No tools found in response or error occurred:", response)
        return self.tools

    async def _continuous_read(self) -> None:
        """Continuously read responses from stdout and resolve pending requests.

        Note:
            TODO: Add exponential backoff and retry logic
            TODO: Implement notification handling
        """
        if not self.process or not self.process.is_running():
            raise RuntimeError("Subprocess not initialized or not running.")
        try:
            while True:
                response = await self.process.read_stdout_nowait()

                if not response:
                    raise RuntimeError("Subprocess stdout closed unexpectedly.")

                return_response = json.loads(response)

                if "id" in return_response and return_response["id"] in self.waiting_requests:
                    print("Response Received for ID:", return_response["id"])
                    future = self.waiting_requests[return_response["id"]]
                    if not future.done():
                        future.set_result(return_response)
                else:
                    print("Notification Received:", response)

        except RuntimeError as re:
            print(f"Runtime error in continuous read: {re}")
            await self._kill_process()
        except json.JSONDecodeError as e:
            print(f"Invalid JSON received")
        except Exception as e:
            print(f"Error in continuous read: {e}")
            await self._kill_process()
    
class HTTPMCPClient(BaseMCPClient):
    """MCP client for HTTP-based server communication."""

    def __init__(self, name:str,  url: str) -> None:
        """Initialize the HTTP MCP client.

        Args:
            url: The HTTP URL of the MCP server
        """
        self.url = url
        self.name = name
        super().__init__()
    
    async def initialize_connection(self) -> dict:
        """Initialize connection to the HTTP MCP server.

        Returns:
            The initialization response from the server

        Note:
            TODO: Add connection pooling
            TODO: Handle streamed JSON
        """
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
                        case _:
                            return {"error": f"Unexpected Content-Type: {content_type}"}

                return {"error": "Stream closed before a valid JSON-RPC message was received."}

            except httpx.RequestError as e:
                return {"error": f"Request Error: {e}"}
            except Exception as e:
                return {"error": f"Unexpected error: {e}"}
    
    async def send_request(self, payload: dict) -> dict:
        """Send a request to the HTTP MCP server (not yet implemented)."""
        return {}

    async def get_tools(self) -> dict:
        """Retrieve tools from the HTTP MCP server (not yet implemented)."""
        return {}

    async def _continuous_read(self) -> None:
        """Continuous read for HTTP client (not yet implemented)."""
        pass
        