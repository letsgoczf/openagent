from __future__ import annotations

import os

from backend.config_loader import OpenAgentSettings, load_config
from backend.models.base import LLMAdapter
from backend.models.ollama_adapter import OllamaAdapter
from backend.models.openai_adapter import OpenAIAdapter
from backend.models.tokenizer import TokenizerService
from backend.models.vllm_adapter import VLLMAdapter


def create_llm_adapter(settings: OpenAgentSettings | None = None) -> LLMAdapter:
    cfg = settings or load_config()
    g = cfg.models.generation
    if g.provider == "openai":
        key = None
        if g.api_key_env:
            key = os.environ.get(g.api_key_env) or None
        return OpenAIAdapter(g.model_id, api_key=key, base_url=g.base_url)
    if g.provider == "ollama":
        return OllamaAdapter(g.model_id, base_url=g.base_url, think=g.think)
    if g.provider == "vllm":
        return VLLMAdapter(
            g.model_id,
            base_url=g.base_url,
            api_key_env=g.api_key_env,
        )
    raise ValueError(f"Unknown generation provider: {g.provider}")


def create_tokenizer_service(settings: OpenAgentSettings | None = None) -> TokenizerService:
    cfg = settings or load_config()
    t = cfg.tokenization
    gen_model = cfg.models.generation.model_id
    if t.provider == "hf":
        msg = "tokenization.provider=hf is not implemented in P1; use auto or tiktoken."
        raise NotImplementedError(msg)
    if t.provider == "tiktoken":
        if not t.tokenizer_model_id:
            msg = "tokenization.tokenizer_model_id is required when provider=tiktoken."
            raise ValueError(msg)
        return TokenizerService(model_id=t.tokenizer_model_id)
    # auto
    if t.tokenizer_model_id:
        return TokenizerService(model_id=t.tokenizer_model_id)
    return TokenizerService(model_id=gen_model)
