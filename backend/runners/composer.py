from __future__ import annotations

from pathlib import Path

from backend.rag.evidence_builder import EvidenceEntry

DEFAULT_CONSTITUTION = """You are OpenAgent, a careful assistant. Use the EVIDENCE section when it contains relevant facts; if evidence is empty or irrelevant, say so and answer from general knowledge without inventing document-specific citations. When evidence is used, align your statements with it."""


def load_constitution_from_file(path: Path | None) -> str:
    if path is None or not path.is_file():
        return DEFAULT_CONSTITUTION
    return path.read_text(encoding="utf-8")


def build_evidence_block(entries: list[EvidenceEntry]) -> str:
    if not entries:
        return "(No retrieved evidence.)"
    lines: list[str] = []
    for i, e in enumerate(entries, start=1):
        lines.append(
            f"[{i}] chunk_id={e.chunk_id} | {e.location_summary} | {e.evidence_snippet_text_v1}"
        )
    return "\n".join(lines)


def build_messages(
    *,
    constitution: str,
    query: str,
    evidence_block: str,
    prompt_addons: list[str] | None = None,
) -> list[dict[str, str]]:
    system = constitution.strip()
    if prompt_addons:
        addon_block = "\n".join(prompt_addons)
        system = system.rstrip() + "\n\n" + addon_block
    user = (
        "EVIDENCE:\n"
        + evidence_block
        + "\n\nUSER QUESTION:\n"
        + query.strip()
        + "\n\nAnswer concisely. If you rely on evidence, mention the bracket numbers [1], [2], … in passing where helpful."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def format_citations_footer(citations: list) -> str:
    """将 citations 拼成可打印脚注（脚本 / CLI）。"""
    if not citations:
        return ""
    lines = ["\n---\nCitations:"]
    for i, c in enumerate(citations, start=1):
        loc = getattr(c, "location_summary", "")
        lines.append(
            f"  [{i}] chunk_id={c.chunk_id} version_id={c.version_id} | {loc}"
        )
    return "\n".join(lines)
