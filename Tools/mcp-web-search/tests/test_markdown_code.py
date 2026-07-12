# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

from core.extract.content_processor import extract_full_body_text
from core.extract.markdown_code import restore_pre_markers
from core.extract.page_normalizer import normalize_page


_PROSE = (
    "This substantial explanatory paragraph keeps the synthetic article on the primary "
    "formatted extraction path while code preservation is verified independently."
)


def test_normalizer_preserves_pre_indentation_and_language():
    html = f"""<html><head><title>Code fixture</title></head><body><article>
    <p>{_PROSE}</p><p>{_PROSE}</p>
    <pre><code class="language-python">async def main():
    await task()
    return 42</code></pre>
    <p>{_PROSE}</p>
    </article></body></html>"""

    markdown = normalize_page("https://fixture.test/code", html)

    assert "```python\nasync def main():\n    await task()\n    return 42\n```" in markdown
    assert "ASLMCODE" not in markdown


def test_normalizer_handles_react_div_line_markup():
    html = f"""<html><head><title>React code fixture</title></head><body><article>
    <p>{_PROSE}</p><p>{_PROSE}</p>
    <pre class="sp-cm sp-pristine sp-javascript"><code>
      <div class="cm-line"><span>function App() {{</span><br></div>
      <div class="cm-line"><span>  return value;</span><br></div>
      <div class="cm-line"><span>}}</span></div>
    </code></pre>
    <p>{_PROSE}</p>
    </article></body></html>"""

    markdown = normalize_page("https://fixture.test/react-code", html)

    assert "```javascript\nfunction App() {\n  return value;\n}\n```" in markdown


def test_dynamic_fence_and_blank_lines_survive_postprocessing():
    html = f"""<html><head><title>Fence fixture</title></head><body><article>
    <p>{_PROSE}</p><p>{_PROSE}</p>
    <pre><code>alpha


```
left | right
--- | ---
omega</code></pre>
    <p>{_PROSE}</p>
    </article></body></html>"""

    markdown = normalize_page("https://fixture.test/fence", html)

    assert "````\nalpha\n\n\n```\nleft | right\n--- | ---\nomega\n````" in markdown
    assert "| left | right |" not in markdown


def test_full_body_fallback_restores_pre_in_place():
    html = """<html><body><header>Download</header>
    <pre><code class="language-shell">if ready; then
  run_command
fi</code></pre>
    <footer>Checksums</footer></body></html>"""

    text = extract_full_body_text(html)

    assert "Download" in text
    assert "```shell\nif ready; then\n  run_command\nfi\n```" in text
    assert "Checksums" in text


def test_marker_boundaries_replace_extractor_generated_code_range():
    start = "ASLMCODESTARTFIXTURE0000END"
    stop = "ASLMCODESTOPFIXTURE0000END"
    extracted = f"{start}\n```\nflattened code\n```\n{stop}"
    inner = "```javascript\nfunction App() {\n  return value;\n}\n```"

    restored = restore_pre_markers(extracted, [(start, stop, inner)])

    assert restored == inner
    assert restored.count("```") == 2
