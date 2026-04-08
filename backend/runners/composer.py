from __future__ import annotations

from pathlib import Path

from backend.rag.evidence_builder import EvidenceEntry
from backend.models.tokenizer import TokenizerService

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


def trim_evidence_entries_to_budget(
    entries: list[EvidenceEntry],
    tokenizer: TokenizerService,
    *,
    max_assembled_tokens: int,
) -> list[EvidenceEntry]:
    """
    组装 EVIDENCE 时做总预算截断，避免“单条已截断但多条合计超上下文”。
    预算口径：近似按每条 snippet token + 少量格式开销累加。
    """
    if max_assembled_tokens <= 0 or not entries:
        return []

    kept: list[EvidenceEntry] = []
    used = 0
    # 格式开销：编号、chunk_id、location 等（粗略常数，不追求完美，只求不爆）
    overhead_per_entry = 36
    for e in entries:
        snip_tok = int(getattr(e, "evidence_entry_tokens_v1", 0) or 0)
        # 对极端情况兜底：若 tokens 字段缺失，现场计数
        if snip_tok <= 0 and e.evidence_snippet_text_v1:
            snip_tok = tokenizer.count_tokens(e.evidence_snippet_text_v1)
        need = snip_tok + overhead_per_entry
        if kept and used + need > max_assembled_tokens:
            break
        if not kept and need > max_assembled_tokens:
            # 至少保留 1 条（即使会略超，也比 0 条好；上游单条已有 max_evidence_entry_tokens 截断）
            kept.append(e)
            break
        kept.append(e)
        used += need
    return kept


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
