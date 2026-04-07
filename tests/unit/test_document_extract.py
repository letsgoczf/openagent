"""文档多格式抽取单测。"""

import pytest

from backend.ingestion.document_extract import (
    DocumentExtractionError,
    extract_document_pages,
)


def test_extract_plain_txt() -> None:
    pages = extract_document_pages(b"hello \n\n world", "notes.txt")
    assert pages == ["hello \n\n world"]


def test_extract_json() -> None:
    pages = extract_document_pages(b'{"a": 1}', "data.json")
    assert len(pages) == 1
    assert '"a": 1' in pages[0]


def test_extract_rtf_minimal() -> None:
    rtf = rb"{\rtf1\ansi hello}"
    pages = extract_document_pages(rtf, "x.rtf")
    assert pages and "hello" in pages[0]


def test_reject_old_doc_magic() -> None:
    # OLE compound doc header
    ole = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100
    with pytest.raises(DocumentExtractionError) as ei:
        extract_document_pages(ole, "legacy.doc")
    assert ".doc" in str(ei.value) or "docx" in str(ei.value).lower() or "OLE" in str(ei.value)


def test_empty_file() -> None:
    with pytest.raises(DocumentExtractionError):
        extract_document_pages(b"", "empty.txt")
