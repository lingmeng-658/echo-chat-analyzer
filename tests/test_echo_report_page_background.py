"""Rendered paper consistency for fictional Echo reports and preview styles."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from qq_chat_analyzer.presentation import export_echo_report_html
from qq_chat_analyzer.presentation.share.renderer import (
    _chromium_flags,
    _run_chromium,
    find_chromium,
)
from test_echo_report_serializer import _echo_view


@pytest.mark.slow_integration
@pytest.mark.parametrize("stylesheet", ["export", "preview"])
@pytest.mark.parametrize("width", [1280, 390])
def test_cover_and_report_pages_render_with_the_same_paper(
    tmp_path: Path, stylesheet: str, width: int,
) -> None:
    chromium = find_chromium()
    if chromium is None:
        pytest.skip("no local Chromium available")
    output = export_echo_report_html(_echo_view(), tmp_path / "report.html")
    html = output.read_text(encoding="utf-8")
    if stylesheet == "preview":
        css = (Path(__file__).resolve().parents[1]
               / "frontend/echo_report/style.css").read_text(encoding="utf-8")
        html = re.sub(r"<style>.*?</style>", lambda _: f"<style>{css}</style>",
                      html, count=1, flags=re.S)
    html = html.replace("</body>", """<script>
const surfaces = Array.from(document.querySelectorAll('.page')).map(node => {
  const style = getComputedStyle(node);
  return [style.backgroundColor, style.backgroundImage, style.opacity];
});
const result = document.createElement('pre');
result.id = 'paper-probe';
result.textContent = JSON.stringify(surfaces);
document.body.appendChild(result);
</script></body>""")
    output.write_text(html, encoding="utf-8")
    result = _run_chromium([
        chromium, *_chromium_flags(tmp_path / "chromium-profile"),
        f"--window-size={width},900", "--dump-dom", output.resolve().as_uri(),
    ], capture_stdout=True)
    assert result.returncode == 0, result.stderr
    match = re.search(r'<pre id="paper-probe">(.*?)</pre>',
                      result.stdout.decode("utf-8"), flags=re.S)
    assert match is not None
    surfaces = json.loads(match.group(1))
    assert len(surfaces) > 1
    assert surfaces[0] == surfaces[1], "cover must share the report paper surface"
    assert all(surface == surfaces[0] for surface in surfaces)
    assert surfaces[0][1:] == ["none", "1"]
