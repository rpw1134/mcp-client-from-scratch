import json

SERVER_URLS = {'example_server': 'https://echo.mcp.inevitable.fyi/mcp', 'local_everything_server_http': 'http://localhost:3001/mcp', 'local_everything_server_stdio': ['npm', ["run", "start"], "/Users/ryanwilliams/Projects/Supplementals/servers/src/everything"]}

INIT_PAYLOAD = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "sampling": {}
            },
            "clientInfo": {
                "name": "ExampleClient",
                "version": "1.0.0"
            }
        }
    }

TOOLS_PAYLOAD = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params":{}
}

INIT_HEADERS = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"
}

EXAMPLE_TOOL_RESPONSE = {
    "params":{
        "name": "add",
        "arguments":{
            "a": 5,
            "b": 4
        }
    }
}

BASE_TOOLS = {
    "chat": {
        "name": "chat",
        "description": "Use this tool to answer general questions or have a conversation.",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The message to return to the user."}
            },
            "required": ["message"],
             "additionalProperties": False
        },
        "source": "native"
    },
    "none":
    {
        "name": "none",
        "description": "Use this tool when no action is needed or the request cannot be fulfilled.",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The reason why no action is taken."}
            },
            "required": ["reason"],
            "additionalProperties": False
        },
        "source": "native"
    },
    "info":
    {
        "name": "info",
        "description": "Use this tool to ask for more information about the user's request if it is unclear or incomplete.",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The message requesting more information from the user."}
            },
            "required": ["reason"],
            "additionalProperties": False
        },
        "source": "native"
    }
}

SYSTEM_PROMPT_BASE = f"You are an AI Agent. Your job is to take in a users request, reference _only_ the available tools as defined below after TOOLS, and decide which tool is best to use given the request. After which, you will populate a json object with necessary properties provided by the users prompt. For example, if a user asks you to add two numbers together -- 5 and 4 -- AND you have access to an addition tool that asks for parameters a and b, respond with\n {json.dumps(EXAMPLE_TOOL_RESPONSE)}\n Do not assume tools exist. Here are a list of rules you _must_ follow:\n 1) You must always respond in the valid JSON format described in the above example. \n2) You must only use the tools defined below after TOOLS. If you may accomplish a task without the use of an explicitly defined tool, you may do so by responding with the 'chat' tool. For example, if I ask you to multiply two numbers, do not respond with a multiplication tool unless it exists; you may instead multiply them on your own. This applies to all kinds of requests. DO NOT MAKE UP TOOLS! If you require more information from the user, whether it is for an explicit tool call or simply for you to gain information to accomplish the task without a tool, use the 'info tool'. If a request cannot and will not be able to be accomplished, use the 'none' tool.\n3) You must only respond with one tool per request. \n4) You must populate all required parameters for a tool. \n5) You must never populate parameters that are not defined for a tool. \n6) You must never alter the name of a tool or parameter. \n7) You must never add additional properties to the JSON object outside of what is defined in the tool parameters. \n8) You must always respond with a valid JSON object that can be parsed by standard JSON parsers.\n\nTOOLS:\n"

