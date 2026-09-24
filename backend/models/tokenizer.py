from __future__ import annotations

import tiktoken


class TokenizerService:
    """tiktoken-backed counting; aligns with evidence-entry token budget (v1 = raw snippet count)."""

    def __init__(
        self,
        *,
        model_id: str | None = None,
        encoding_name: str | None = None,
    ) -> None:
        if encoding_name:
            self._enc = tiktoken.get_encoding(encoding_name)
            self._tokenizer_id = f"tiktoken:{encoding_name}"
        elif model_id:
            try:
                self._enc = tiktoken.encoding_for_model(model_id)
                self._tokenizer_id = f"tiktoken:model:{model_id}"
            except KeyError:
                self._enc = tiktoken.get_encoding("cl100k_base")
                self._tokenizer_id = "tiktoken:cl100k_base"
        else:
            self._enc = tiktoken.get_encoding("cl100k_base")
            self._tokenizer_id = "tiktoken:cl100k_base"

    @property
    def tokenizer_id(self) -> str:
        return self._tokenizer_id

    def count_tokens(self, text: str) -> int:
        if not text:
            return 0
        return len(self.encode(text))

    def encode(self, text: str) -> list[int]:
        """Return token ids for `text` using configured encoding.

        tiktoken raises ValueError when text contains a special token such as
        ``<|endoftext|>`` unless those tokens are explicitly allowed. Chat
        transcripts, model output, and imported documents often include them.
        Treat them as ordinary characters so counting and chunking cannot abort
        a turn or an import.
        """
        if not text:
            return []
        return list(self._enc.encode(text, disallowed_special=()))

    def decode(self, tokens: list[int]) -> str:
        """Decode token ids back into text."""
        if not tokens:
            return ""
        return self._enc.decode(tokens)

    def count_evidence_entry_tokens_v1(self, snippet: str) -> int:
        """EvidenceEntry v1: count snippet body only (template wrapper added later in rag layer)."""
        return self.count_tokens(snippet)
