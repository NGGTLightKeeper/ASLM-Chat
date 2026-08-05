# Copyright NEXTGGTECH. Elastic License 2.0.

"""thin→full-body rescue — ported behaviour from openserp's extractFullBody fallback.

The clean pass (preclean strips nav/header/footer/form/button, trafilatura keeps only the
"article") guts pages whose chrome IS the information: landing pages, doc indexes, download
pages. When the cleaned result is near-empty but the page carried more visible text,
normalize_page must return the whole readable body instead of a husk.
"""

from __future__ import annotations

from core.extract.content_processor import extract_full_body_text
from core.extract.page_normalizer import normalize_page

# A download-landing-page shape: all real information lives in nav/header/footer/buttons,
# which the strict clean pass removes wholesale.
_LANDING = """<html><head><title>Get ExampleApp</title></head><body>
<header><h1>ExampleApp</h1><nav>
<a href="/download/windows">Download for Windows 11/10</a>
<a href="/download/mac">Download for macOS</a>
<a href="/download/linux">Download for Linux (.deb/.rpm)</a>
<a href="/enterprise">Enterprise deployment</a>
</nav></header>
<main><button>Download ExampleApp</button><p>Version 5.2 · 84 MB</p></main>
<footer><a href="/checksums">SHA-256 checksums</a><a href="/releases">All releases</a></footer>
<script>var telemetry = "should never appear";</script>
<style>.x{color:red}</style>
</body></html>"""


def test_full_body_keeps_nav_and_buttons_strips_machinery():
    text = extract_full_body_text(_LANDING)
    assert "Download for Windows 11/10" in text
    assert "SHA-256 checksums" in text          # footer kept
    assert "Download ExampleApp" in text        # button kept
    assert "should never appear" not in text    # script stripped
    assert ".x{color:red}" not in text          # style stripped


def test_normalize_page_rescues_landing_page():
    md = normalize_page("https://example.com/download", _LANDING)
    # Without the rescue this page normalizes to "*No content extracted.*" or a husk.
    assert "Download for Windows 11/10" in md
    assert "Enterprise deployment" in md
    assert "*No content extracted.*" not in md


def test_normalize_page_keeps_clean_extraction_for_articles():
    paras = "".join(
        f"<p>Paragraph {i} carries substantial article prose about the subject, "
        "long enough to stay a real content block after cleaning.</p>"
        for i in range(12)
    )
    html = (
        "<html><head><title>Real article</title></head><body>"
        f"<nav><a href='/'>Home</a><a href='/tags'>Tags</a></nav><article>{paras}</article>"
        "</body></html>"
    )
    md = normalize_page("https://example.com/article", html)
    assert "Paragraph 3 carries substantial article prose" in md
    # Clean pass was rich → no rescue → nav chrome must NOT leak into the output.
    assert "Tags" not in md


def test_full_body_empty_and_broken_inputs():
    assert extract_full_body_text("") == ""
    assert "hello" in extract_full_body_text("<p>hello broken <div>world")


def test_rescue_not_triggered_when_body_adds_nothing():
    # Cleaned result is thin AND the body has no more text → keep the honest sentinel.
    html = "<html><body><p>tiny</p></body></html>"
    md = normalize_page("https://example.com/x", html)
    assert "tiny" in md
