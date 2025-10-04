import os
from openai import OpenAI
import json
from collections import OrderedDict
from .constants import SYSTEM_PROMPT_BASE, EXECUTE_PAYLOAD_TEMPLATE
from ..classes.MCPClient import STDIOMCPClient

def AI_request(client: STDIOMCPClient, message: str) -> dict:
    """Make an AI request to determine which tool to use.

    Args:
        client: The STDIO MCP client (used to reference available tools)
        message: The user's message

    Returns:
        Dictionary containing the parsed tool request

    Note:
        TODO: This will be changed once session logic is in place
    """
    try:
        key = os.getenv("OPEN_AI_API_KEY")
        if not key:
            raise ValueError("OPEN_AI_API_KEY environment variable not set.")
        openai = OpenAI(api_key=key)
        response = openai.chat.completions.create(
            model="gpt-5-nano",
            messages=[{"role": "system", "content": _get_system_prompt(client)}, {"role": "user", "content": message}, ],
            max_completion_tokens=10000,
        )
        res = response.choices[0].message.content or ""
    except Exception as e:
        res = f"Error during AI request: {e}"
    return _response_to_dict(res)

def _get_system_prompt(client: STDIOMCPClient) -> str:
    """Generate the system prompt with available tools.

    Args:
        client: The STDIO MCP client

    Returns:
        The complete system prompt
    """
    return SYSTEM_PROMPT_BASE + str(client.tools)

def _response_to_dict(response: str) -> dict:
    """Parse AI response into a dictionary and augment server tools with execution template.

    Args:
        response: The AI response string

    Returns:
        Parsed response dictionary

    Raises:
        ValueError: If response is not valid JSON
    """
    try:
        res = json.loads(response, object_pairs_hook=OrderedDict)
        if "source" in res and res["source"] == "server":
            res |= EXECUTE_PAYLOAD_TEMPLATE.copy()
        return res
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse response as JSON: {e}")

