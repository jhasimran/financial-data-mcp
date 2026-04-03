from pathlib import Path

import pytest

from app.tools.ingestion import ingest_financial_documents


class DummyPage:
    def __init__(self, text: str):
        self._text = text

    def extract_text(self) -> str:
        return self._text


class DummyPdf:
    def __init__(self, pages: list[DummyPage]):
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_ingestion_extracts_and_normalizes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    sample_pdf = tmp_path / "statement.pdf"
    sample_pdf.write_text("placeholder")

    def fake_open(path: Path):
        return DummyPdf(
            [
                DummyPage(
                    "03/21 Starbucks -5.67\n03/22 Payroll 3500.00\n"
                )
            ]
        )

    monkeypatch.setattr("app.tools.ingestion.pdfplumber.open", fake_open)

    result = ingest_financial_documents([str(sample_pdf)])
    assert result["count"] == 2
    assert result["sources"] == 1
    assert result["transactions"][0]["direction"] in {"debit", "credit"}


def test_ingestion_sanitizes_pii_like_patterns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sample_pdf = tmp_path / "statement.pdf"
    sample_pdf.write_text("placeholder")

    def fake_open(path: Path):
        return DummyPdf(
            [
                DummyPage(
                    "03/21 John Doe 123456789012 john@doe.com 123 Main St -12.50"
                )
            ]
        )

    monkeypatch.setattr("app.tools.ingestion.pdfplumber.open", fake_open)

    result = ingest_financial_documents([str(sample_pdf)])
    merchant = result["transactions"][0]["merchant"]
    assert "[redacted-number]" in merchant
    assert "[redacted-email]" in merchant
    assert "[redacted-address]" in merchant


def test_ingestion_handles_non_pdf_and_missing_files(tmp_path: Path) -> None:
    txt_file = tmp_path / "note.txt"
    txt_file.write_text("nope")
    result = ingest_financial_documents([str(txt_file), str(tmp_path / "missing.pdf")])
    assert result["count"] == 0
    assert len(result["warnings"]) >= 1


def test_ingestion_requires_paths() -> None:
    with pytest.raises(ValueError, match="at least one PDF"):
        ingest_financial_documents([])
