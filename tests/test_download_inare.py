from __future__ import annotations

import time

from scripts.download.companies.reasuransi.inare import (
    SOURCE_URL,
    choose_candidate,
    discover_candidates,
    validate_pdf_bytes,
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

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, responses: dict[str, FakeResponse]) -> None:
        self.responses = responses
        self.headers: dict[str, str] = {}

    def get(self, url: str, **kwargs):  # noqa: ANN001
        try:
            return self.responses[url]
        except KeyError as exc:  # pragma: no cover - defensive.
            raise AssertionError(f"unexpected URL requested: {url}") from exc


def test_discovers_only_conventional_report() -> None:
    conventional_pdf = "https://inare.co.id/uploads/2026/03/target.pdf"
    syariah_pdf = "https://inare.co.id/uploads/2026/04/96b84015712bb3773363c5d7f676db48_syariah.pdf"
    annual_pdf = "https://inare.co.id/uploads/2026/04/annual-2025.pdf"

    html = f"""
    <html>
      <head><title>Laporan Keuangan Bulanan | Inare</title></head>
      <body>
        <section class="financial-report">
          <article>
            <div>15 April 2026</div>
            <h3>Laporan Keuangan Bukan Konsolidasi per Maret 2026 dan 2025 Syariah</h3>
            <a href="{syariah_pdf}"><img alt="download" /></a>
          </article>
          <article>
            <div>15 April 2025</div>
            <h3>Laporan Tahunan 2025</h3>
            <a href="{annual_pdf}"><img alt="download" /></a>
          </article>
          <nav class="pagination">
            <a href="{SOURCE_URL}?page=2">Next ></a>
          </nav>
        </section>
      </body>
    </html>
    """
    session = FakeSession(
        {
            SOURCE_URL: FakeResponse(
                url=SOURCE_URL,
                headers={"Content-Type": "text/html; charset=utf-8"},
                text=html,
            ),
            f"{SOURCE_URL}?page=2": FakeResponse(
                url=f"{SOURCE_URL}?page=2",
                headers={"Content-Type": "text/html; charset=utf-8"},
                text=f"""
                <html>
                  <body>
                    <article>
                      <div>15 March 2026</div>
                      <h3>Laporan Keuangan Bukan Konsolidasi per Maret 2026 dan 2025</h3>
                      <a href="{conventional_pdf}"><img alt="download" /></a>
                    </article>
                  </body>
                </html>
                """,
            ),
        }
    )

    candidates, snapshots, source_html, rendered_html = discover_candidates(
        session,
        SOURCE_URL,
        2026,
        3,
        use_browser=False,
        timeout=10,
        max_pages=4,
        max_depth=4,
        deadline=time.monotonic() + 10,
    )

    assert len(snapshots) == 1
    assert source_html
    assert rendered_html == ""
    assert len(candidates) == 1
    best = choose_candidate(candidates)
    assert best is not None
    assert best.pdf_url == conventional_pdf
    assert best.target_match


def test_validate_pdf_bytes() -> None:
    assert validate_pdf_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\n%%EOF")
    assert not validate_pdf_bytes(b"<html><body>not a pdf</body></html>")
