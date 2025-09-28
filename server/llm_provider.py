# LLM_PROVIDER_V1
import os
from typing import AsyncGenerator, List, Dict, Any
from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

async def stream_response(messages: List[Dict[str, Any]]) -> AsyncGenerator[str, None]:
    """
    Streams tokens from OpenAI Chat Completions.
    Falls back to echo-mode if no API key is present.
    """
    if not OPENAI_API_KEY:
        user_last = next((m["content"] for m in reversed(messages) if m["role"]=="user"), "")
        yield f"(echo) {user_last}"
        return

    client = AsyncOpenAI(api_key=OPENAI_API_KEY)

    stream = await client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
        stream=True,
    )
    async for event in stream:
        for choice in event.choices:
            delta = getattr(choice, "delta", None)
            if delta and getattr(delta, "content", None):
                yield delta.content
