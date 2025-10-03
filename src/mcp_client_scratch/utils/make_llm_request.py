import os
from openai import OpenAI
from .constants import SYSTEM_PROMPT_BASE
from ..classes.MCPClient import STDIOMCPClient

# Will be changed once session logic is in place, for now just pass the client to reference tools
def AI_request(client: STDIOMCPClient, message: str) -> str:
    try:
        key = os.getenv("OPEN_AI_API_KEY")
        if not key:
            raise ValueError("OPEN_AI_API_KEY environment variable not set.")
        openai = OpenAI(api_key=key)
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": get_system_prompt(client)}, {"role": "user", "content": message}, ],
            max_tokens=500,
            temperature=0.7,
        )
        res = response.choices[0].message.content or ""
    except Exception as e:
        res = f"Error during AI request: {e}"
    return res

def get_system_prompt(client: STDIOMCPClient) -> str:
    return SYSTEM_PROMPT_BASE + str(client.tools)

