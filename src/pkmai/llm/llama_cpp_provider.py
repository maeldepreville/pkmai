import json
import logging
from pathlib import Path
from typing import Any, cast

from llama_cpp import Llama

from pkmai.llm.base import BaseLLM


class LlamaCppProvider(BaseLLM):
    """
    Local LLM provider using llama.cpp to generate structured JSON.
    """

    def __init__(self, model_path: Path, n_ctx: int = 4096, n_threads: int = 4):
        logging.info("Initializing Llama model from: %s", model_path)
        self.llm = Llama(
            model_path=str(model_path), n_ctx=n_ctx, n_threads=n_threads, verbose=False
        )

    def generate_json(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 1024,
        temperature: float = 0.3,
        repeat_penalty: float = 1.15,
    ) -> dict[str, Any]:

        logging.info("Starting LLM generation...")

        response = cast(dict[str, Any], self.llm.create_chat_completion(
            messages=cast(list[Any], messages),
            max_tokens=max_tokens,
            temperature=temperature,
            repeat_penalty=repeat_penalty,
            response_format={"type": "json_object"} 
        ))

        logging.info("Successfully generated LLM response.")

        raw_content = response["choices"][0]["message"].get("content")
        text = raw_content.strip() if raw_content else ""

        if not text:
            raise ValueError("Empty response from the model.")

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Invalid JSON returned by the model: {e}\nRaw content:\n{text}"
            ) from e
