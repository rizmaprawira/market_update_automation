from __future__ import annotations

from pathlib import Path

from scripts.download.download_general_insurance import (
    choose_best_candidate,
    download_pdf,
    extract_pdf_candidates,
    is_relevant_financial_report,
    is_syariah_candidate,
    normalize_month_terms,
    sanitize_filename,
)


class FakeResponse:
    def __init__(
        self,
        *,
        url: str,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        text: str = "",
        content: bytes | None = None,
    ) -> None:
        self.url = url
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text
        self.content = content if content is not None else text.encode("utf-8")
        self._chunks = [self.content[i : i + 8192] for i in range(0, len(self.content), 8192)] or [b""]

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size: int = 8192):
        yield from self._chunks

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class FakeSession:
    def __init__(self, responses: dict[str, FakeResponse]) -> None:
        self.responses = responses
        self.headers: dict[str, str] = {}
        self._download_timeout = 30

    def get(self, url: str, **kwargs):  # noqa: ANN001
        try:
            return self.responses[url]
        except KeyError as exc:
            raise AssertionError(f"unexpected URL requested: {url}") from exc


def test_month_terms_and_sanitizer() -> None:
    assert normalize_month_terms(4) == ["april", "apr", "4", "04"]
    assert sanitize_filename("PT Asuransi Bintang Tbk") == "asuransi_bintang"


def test_syariah_detection_and_relevance() -> None:
    assert is_syariah_candidate("Laporan Keuangan Syariah UUS")
    assert is_syariah_candidate("Sharia Financial Statement")
    assert is_relevant_financial_report("Laporan Keuangan Konvensional April 2026", 2026, 4)
    assert not is_relevant_financial_report("Laporan Keuangan Syariah April 2026", 2026, 4)


def test_extract_and_choose_candidate_with_recursive_html() -> None:
    root_url = "https://example.com/reports"
    nested_url = "https://example.com/reports/conventional-index"
    conventional_pdf = "https://example.com/pdfs/company_april_2026.pdf"
    syariah_pdf = "https://example.com/pdfs/company_april_2026_syariah.pdf"

    root_html = f"""
    <html>
      <head><title>Financial Highlights</title></head>
      <body>
        <a href="{nested_url}">Laporan Keuangan</a>
        <a href="https://example.com/syariah-index">Laporan Keuangan Syariah</a>
      </body>
    </html>
    """
    nested_html = f"""
    <html>
      <head><title>Report Index</title></head>
      <body>
        <a href="{conventional_pdf}">Laporan Keuangan Perusahaan April 2026</a>
        <a href="{syariah_pdf}">Laporan Keuangan Syariah April 2026</a>
      </body>
    </html>
    """

    responses = {
        root_url: FakeResponse(url=root_url, headers={"Content-Type": "text/html"}, text=root_html),
        nested_url: FakeResponse(url=nested_url, headers={"Content-Type": "text/html"}, text=nested_html),
        conventional_pdf: FakeResponse(
            url=conventional_pdf,
            headers={"Content-Type": "application/pdf"},
            content=b"%PDF-1.4 conventional report",
        ),
    }
    session = FakeSession(responses)

    candidates = extract_pdf_candidates(session, root_url, 2026, 4, use_browser=False)
    assert any(candidate["pdf_url"] == conventional_pdf for candidate in candidates)
    assert any(candidate["pdf_url"] == syariah_pdf for candidate in candidates)

    best = choose_best_candidate(candidates, 2026, 4)
    assert best is not None
    assert best["pdf_url"] == conventional_pdf
    assert not best["is_syariah"]


def test_download_pdf_writes_file(tmp_path: Path) -> None:
    pdf_url = "https://example.com/pdfs/company_april_2026.pdf"
    output_path = tmp_path / "company_april_2026.pdf"

    responses = {
        pdf_url: FakeResponse(
            url=pdf_url,
            headers={"Content-Type": "application/pdf"},
            content=b"%PDF-1.4 fake report bytes",
        )
    }
    session = FakeSession(responses)

    result = download_pdf(session, pdf_url, output_path, timeout=30, force=False)
    assert result["status"] == "downloaded"
    assert output_path.exists()
    assert output_path.read_bytes().startswith(b"%PDF")
