from __future__ import annotations

import os

from backend.models.openai_adapter import OpenAIAdapter


class VLLMAdapter(OpenAIAdapter):
    """vLLM OpenAI-compatible server (same HTTP API as OpenAI chat completions)."""

    def __init__(
        self,
        model_id: str,
        *,
        base_url: str | None = None,
        api_key_env: str | None = None,
    ) -> None:
        if not base_url:
            msg = "vLLM requires models.generation.base_url (OpenAPI v1 base)."
            raise ValueError(msg)
        key: str | None = None
        if api_key_env:
            key = os.environ.get(api_key_env) or None
        super().__init__(model_id, api_key=key, base_url=base_url)
