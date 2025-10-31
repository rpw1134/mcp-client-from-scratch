from ..utils.constants import INIT_HEADERS, INIT_PAYLOAD, TOOLS_PAYLOAD, EXECUTE_PAYLOAD_TEMPLATE
from ..utils.parse_responses import parse_sse, poll_sse, parse_batched_sse
import json
import asyncio
import httpx
import logging
from abc import ABC, abstractmethod
from .Process import Process
from typing import Optional, Union

logger = logging.getLogger("uvicorn.error")

class BaseMCPClient(ABC):
    """Abstract base class for MCP client implementations."""

    def __init__(self) -> None:
        """Initialize the base MCP client."""
        self.current_id: int = 1
        self.waiting_requests: dict[int, asyncio.Future] = {}
        self.tools: dict[str,dict] = {}
        self.name = ""
    
    @abstractmethod
    async def initialize_connection(self) -> dict:
        """Initialize connection to the MCP server."""
        pass

    @abstractmethod
    async def send_request(self, tool_params: dict, function: str) -> dict:
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
            self.tools[tool["name"]]["source"] = self.name
    
    def get_tool_by_name(self, tool_name: str) -> Optional[dict]:
        """Retrieve a tool by its name.

        Args:
            tool_name: Name of the tool to retrieve

        Returns:
            The tool dictionary if found, else None
        """
        return self.tools.get(tool_name, None)
        
        
    
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
            self.process = Process(command=full_command, wkdir=self.wkdir, env=self.env)
            await self.process.start()
            await self.process.read_startup_notifications()

        except Exception as e:
            logger.error(f"Failed to start subprocess: {e}", exc_info=True)
            raise RuntimeError(f"Failed to start subprocess: {e}")
    
    async def kill_process(self) -> int:
        """Terminate the subprocess.

        Returns:
            Return code of the terminated process, or -1 if error
        """
        try:
            return await self.process.terminate()
        except Exception as e:
            logger.error(f"Error terminating subprocess: {e}")
            return -1
    
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
            await self.send_notification("notifications/initialized", {"status": "ready"})
            asyncio.create_task(self._continuous_read())
            self.current_id += 1

            return json.loads(response) if response else {}

        except Exception as e:
            await self.kill_process()
            return {"error": f"Failed to send initialization message: {e}"}
        
    async def send_request(self, tool_params: dict, function: str) -> dict:
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
            if function == "get":
                payload = {**TOOLS_PAYLOAD}
            else:
                payload = {**EXECUTE_PAYLOAD_TEMPLATE}
            curr_id = self.current_id
            self.current_id += 1
            payload["params"] = tool_params
            payload["id"] = curr_id
            request = json.dumps(payload)
            print(request)
            await self.process.write_stdin(request)

            self.waiting_requests[curr_id] = asyncio.Future()
            response = await asyncio.wait_for(self.waiting_requests[curr_id], timeout=10.0)

            del self.waiting_requests[curr_id]

        except RuntimeError as e:
            await self.kill_process()
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
            logger.warning(f"Failed to send notification: {e}")

    
    async def get_tools(self) -> dict:
        """Retrieve and store available tools from the MCP server.

        Returns:
            Dictionary of available tools
        """
        response = await self.send_request({}, function="get")
        if "result" in response and "tools" in response["result"]:
            self._set_tools(response["result"]["tools"])
        else:
            logger.warning(f"No tools found in response or error occurred: {response}")
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
                    break

                return_response = json.loads(response)

                if "id" in return_response and return_response["id"] in self.waiting_requests:
                    future = self.waiting_requests[return_response["id"]]
                    if not future.done():
                        future.set_result(return_response)
                else:
                    logger.debug(f"Notification: {return_response}")

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON received in continuous read")
        except Exception as e:
            logger.error(f"Error in continuous read: {e}")
            await self.kill_process()
    
class HTTPMCPClient(BaseMCPClient):
    """MCP client for HTTP-based server communication."""

    def __init__(self, name:str,  url: str, headers: Optional[dict[str,str]] = None) -> None:
        """Initialize the HTTP MCP client.

        Args:
            name: Name of the MCP server
            url: The HTTP URL of the MCP server
            headers: Optional custom headers to include in requests
        """
        super().__init__()
        self.name = name
        self.url = url
        self.httpx_client: Optional[httpx.AsyncClient] = None
        self.notification_stream: Optional[httpx.Response] = None
        self.custom_headers = headers or {}
        self.mcp_session_id: Optional[str] = None

    def _build_headers(self, additional_headers: Optional[dict[str, str]] = None) -> dict[str, str]:
        """Build request headers, including session ID if available.

        Args:
            additional_headers: Optional headers to merge

        Returns:
            Merged headers dict with no None values
        """
        headers = {**self.custom_headers}

        if additional_headers:
            headers.update(additional_headers)

        # Add session ID only if it's set
        if self.mcp_session_id:
            headers["Mcp-Session-Id"] = self.mcp_session_id

        return headers

    async def initialize_connection(self) -> dict:
        """Initialize connection to the HTTP MCP server.

        Returns:
            The initialization response from the server

        Note:
            TODO: Add connection pooling
            TODO: Handle streamed JSON
        """
        client = self.httpx_client = httpx.AsyncClient(headers=self._build_headers(INIT_HEADERS), timeout=httpx.Timeout(10.0, read=None))
        try:
            response = await client.stream("POST", self.url, json=INIT_PAYLOAD).__aenter__()
            content_type = response.headers.get("Content-Type", "")
            self.mcp_session_id = response.headers.get("Mcp-Session-Id")
            self.current_id += 1

            match content_type:
                # if server uses SSE for streaming responses, open notifaction channel and return the initialization response
                case "text/event-stream":
                    res = await parse_sse(response)
                    if "id" not in res:
                        raise RuntimeError("No valid JSON-RPC message received during initialization.")
                    message = res
                    await self.send_notification("notifications/initialized", {"status": "ready"})
                    asyncio.create_task(self._continuous_read())

                # otherwise, expect a normal JSON response for initialization
                case "application/json":
                    message = await response.json()
                    await self.send_notification("notifications/initialized", {"status": "ready"})
                case _:
                    return {"error": f"Unexpected Content-Type: {content_type}"}
            return message

        except httpx.RequestError as e:
            return {"error": f"Request Error: {e}"}
        except Exception as e:
            return {"error": f"Unexpected error: {e}"}
    
    async def send_request(self, tool_params: dict, function: str) -> dict:
        try:
            if not self.httpx_client:
                raise RuntimeError("HTTP connection not initialized.")
            if function == "get":
                payload = {**TOOLS_PAYLOAD}
            else:
                payload = {**EXECUTE_PAYLOAD_TEMPLATE}
            curr_id = self.current_id
            self.current_id += 1
            payload["params"] = tool_params
            payload["id"] = curr_id
            async with self.httpx_client.stream("POST", self.url, json=payload, headers=self._build_headers()) as response:
                content_type = response.headers.get("Content-Type", "")
                match content_type:
                    case "application/json":
                        return await response.json()
                    case "text/event-stream":
                        return await parse_sse(response)
                    case _:
                        raise RuntimeError(f"Unexpected Content-Type: {content_type}")
        except RuntimeError as re:
            return {"error": f"Runtime error: {re}"}
        return {}

    async def get_tools(self) -> dict:
        """Retrieve tools from the HTTP MCP server."""
        response = await self.send_request({}, function="get")
        if "result" in response and "tools" in response["result"]:
            self._set_tools(response["result"]["tools"])
        else:
            logger.warning(f"No tools found in response: {response}")
        return self.tools

    async def _continuous_read(self) -> None:
        """Continuous read for HTTP client (not yet implemented)."""
        try:
            if not self.httpx_client:
                raise RuntimeError("HTTP connection not initialized.")
            async with self.httpx_client.stream("GET", self.url, headers=self._build_headers()) as response:
                self.notification_stream = response
                if not self.notification_stream:
                    raise RuntimeError("Notification stream not initialized")
                await poll_sse(self.notification_stream, self.waiting_requests)
        except RuntimeError as re:
            logger.warning(f"HTTP continuous read closed: {re}")
        except Exception as e:
            logger.error(f"Error in HTTP continuous read: {e}")
        
    async def send_notification(self, method: str, params: dict = {}) -> None:
        """Send a JSON-RPC notification to the MCP server.

        Args:
            method: The notification method
            params: The notification parameters
        """
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }

        try:
            if not self.httpx_client:
                raise RuntimeError("HTTP connection not initialized.")
            response = await self.httpx_client.post(self.url, json=notification, headers=self._build_headers())
            if response.status_code != 202:
                logger.warning(f"Notification '{method}' failed: status {response.status_code}")

        except Exception as e:
            logger.warning(f"Failed to send notification '{method}': {e}")
    
    async def close_connection(self) -> None:
        try:
            if self.notification_stream:
                await self.notification_stream.aclose()
            if self.httpx_client:
                await self.httpx_client.aclose()
        except Exception as e:
            logger.error(f"Error closing HTTP connection: {e}")
        