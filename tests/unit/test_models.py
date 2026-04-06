from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.models.factory import create_tokenizer_service
from backend.models.openai_adapter import OpenAIAdapter
from backend.models.tokenizer import TokenizerService


def test_tokenizer_count_positive() -> None:
    t = TokenizerService(model_id="gpt-4")
    n = t.count_tokens("hello world")
    assert isinstance(n, int)
    assert n > 0


def test_tokenizer_evidence_v1_same_as_count() -> None:
    t = TokenizerService(encoding_name="cl100k_base")
    s = "evidence snippet"
    assert t.count_evidence_entry_tokens_v1(s) == t.count_tokens(s)


def test_factory_tokenizer_uses_config() -> None:
    from backend.config_loader import OpenAgentSettings, GenerationConfig, ModelsConfig
    from backend.config_loader import TokenizationConfig

    cfg = OpenAgentSettings(
        models=ModelsConfig(
            generation=GenerationConfig(
                provider="ollama",
                model_id="llama3.2",
                base_url="http://127.0.0.1:11434",
            ),
        ),
        tokenization=TokenizationConfig(provider="auto", tokenizer_model_id=None),
    )
    t = create_tokenizer_service(cfg)
    assert t.count_tokens("a") >= 1


def test_openai_adapter_streams_deltas() -> None:
    chunk_mock = MagicMock()
    chunk_mock.choices = [MagicMock()]
    chunk_mock.choices[0].delta.content = "hi"

    stream_iter = [chunk_mock]

    create_mock = MagicMock(return_value=iter(stream_iter))

    with patch("backend.models.openai_adapter.OpenAI") as client_cls:
        instance = MagicMock()
        instance.chat.completions.create = create_mock
        client_cls.return_value = instance

        ad = OpenAIAdapter("gpt-4o-mini", api_key="k")
        out = ad.chat([{"role": "user", "content": "x"}], stream=True)
        parts = list(out)  # type: ignore[arg-type]
        assert parts == [("content", "hi")]
        create_mock.assert_called_once()
        call_kw = create_mock.call_args.kwargs
        assert call_kw["stream"] is True
