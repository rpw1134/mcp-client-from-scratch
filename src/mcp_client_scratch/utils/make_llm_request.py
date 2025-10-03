import os
from openai import OpenAI


def AI_request(message: str) -> str:
    try:
        key = os.getenv("OPEN_AI_API_KEY")
        if not key:
            raise ValueError("OPEN_AI_API_KEY environment variable not set.")
        openai = OpenAI(api_key=key)
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": message}],
            max_tokens=500,
            temperature=0.7,
        )
        res = response.choices[0].message.content or ""
    except Exception as e:
        res = f"Error during AI request: {e}"
    return res