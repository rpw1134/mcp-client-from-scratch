import json
import httpx
import asyncio

async def parse_sse(response: httpx.Response) -> dict:
    """Parse Server-Sent Events (SSE) stream for JSON-RPC messages.

    Args:
        response: The HTTP response with SSE stream

    Returns:
        The first valid JSON-RPC message found, or an error dictionary
    """
    async for line in response.aiter_lines():
        if line.strip() == "":
            continue
        if line.startswith("data:"):
            data = line[len("data:"):].strip()
            try:
                message = json.loads(data)
                if "jsonrpc" in message and "id" in message:
                    print("Received valid JSON-RPC message:", message)
                    return message
                else:
                    print("Received non-JSON-RPC message:", message)
            except json.JSONDecodeError:
                print("Received non-JSON data:", data)
                continue
    return json.loads("{error: 'No valid JSON-RPC message received'}")

async def poll_sse(response: httpx.Response, pending_requests: dict[int, asyncio.Future]) -> None:
    """Poll Server-Sent Events (SSE) stream for JSON-RPC messages. Specifically for notifications.

    Args:
        response: The HTTP response with SSE stream

    Returns:
        None
    """
    try:
        print("NOTIFICATIONS POLLING STARTED")
        async for line in response.aiter_lines():
            if line.strip() == "":
                continue
            if line.startswith("data:"):
                data = line[len("data:"):].strip()
                try:
                    message = json.loads(data)
                    if "jsonrpc" in message:
                        print("Received valid JSON-RPC message:", message)
                        if "id" in message and message["id"] in pending_requests:
                            pending_requests[message["id"]].set_result(message)
                    else:
                        print("Received non-JSON-RPC message:", message)
                except json.JSONDecodeError:
                    print("Received non-JSON data:", data)
                    continue
        raise RuntimeError("SSE stream closed")
    except Exception as e:
        print(f"Error while polling SSE or stream closed on one end: {e}")
        
async def parse_batched_sse(response: httpx.Response) -> list:
    """Parse Server-Sent Events (SSE) stream for batched JSON-RPC messages.

    Args:
        response: The HTTP response with SSE stream
    Returns:
        List of JSON-RPC messages found
    """
    messages = []
    try:
        async for line in response.aiter_lines():
            if line.strip()=="":
                continue
            if line.startswith("data:"):
                data = line[len("data:"):].strip()
                try:
                    res = json.loads(data)
                    if isinstance(res, list):
                        messages.extend(res)
                        print(f"Received batched JSON-RPC messages: {res}")
                    elif "jsonrpc" in res:
                        messages.append(res)
                        print(f"Received valid JSON-RPC message: {res}")
                    else:
                        print(f"Received non-JSON-RPC message: {res}")
                except json.JSONDecodeError:
                    print("Received non-JSON data:", data)
                    continue
    except Exception as e:
        print(e)
    finally:
        return messages
        



async def parse_tool_arguments(response: dict) -> list:
    """Extract tool arguments from a response dictionary.

    Args:
        response: The response dictionary containing params and arguments

    Returns:
        List of argument values
    """
    ret_list = []
    print("PARSING ARGS")
    if "params" in response and "arguments" in response["params"]:
        for value in response["params"]["arguments"].values():
            ret_list.append(value)
    return ret_list

async def parse_response_for_jrpc(response: dict) -> dict:
    """Remove the source field from a response dictionary for JSON-RPC compatibility.

    Args:
        response: The response dictionary

    Returns:
        Response dictionary without the source field
    """
    del response["source"]
    return response