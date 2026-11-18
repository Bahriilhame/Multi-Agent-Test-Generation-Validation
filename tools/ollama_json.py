"""Ollama client helper for structured JSON-only critic responses."""

import asyncio

from langchain_ollama import ChatOllama

from tools.llm_client import (
    BASE_URL,
    MAX_OUTPUT_TOKENS,
    MODEL_NAME,
    REQUEST_TIMEOUT_SECONDS,
)


def get_json_llm(timeout_seconds: float | None = None, max_output_tokens: int | None = None):
    timeout = timeout_seconds or REQUEST_TIMEOUT_SECONDS
    return ChatOllama(
        model=MODEL_NAME,
        base_url=BASE_URL,
        temperature=0,
        num_predict=max_output_tokens or MAX_OUTPUT_TOKENS,
        format="json",
        client_kwargs={"timeout": timeout},
        async_client_kwargs={"timeout": timeout},
    )


def ask_llm_json(
    prompt: str,
    *,
    timeout_seconds: float = 180,
    wall_timeout_seconds: float = 180,
    max_output_tokens: int = 350,
) -> str:
    async def invoke() -> str:
        model = get_json_llm(timeout_seconds, max_output_tokens)
        response = await asyncio.wait_for(model.ainvoke(prompt), timeout=wall_timeout_seconds)
        return response.content

    try:
        return asyncio.run(invoke())
    except TimeoutError as error:
        raise TimeoutError(f"Ollama JSON review exceeded {wall_timeout_seconds:g} seconds.") from error
