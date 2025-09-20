import os, openai


def AI_request(message: str) -> str:
    openai.api_key = os.getenv("OPEN_AI_API_KEY")
    response = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": message}],
        max_tokens=500,
        temperature=0.7,
    )
    res = response.choices[0].message.content or ""
    return res