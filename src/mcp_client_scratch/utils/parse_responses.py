import json
import httpx

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
        print("RAW LINE:", line)
        if line.startswith("data:"):
            data = line[len("data:"):].strip()
            print("DATA:", data)
            try:
                message = json.loads(data)
                if "jsonrpc" in message and "id" in message:
                    print("valid")
                    return message
                else:
                    print("Received non-JSON-RPC message:", message)
            except json.JSONDecodeError:
                print("Received non-JSON data:", data)
                continue
    return json.loads("{error: 'No valid JSON-RPC message received'}")

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