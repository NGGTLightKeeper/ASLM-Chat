"""End-to-end capability smoke tests for the sandbox tool."""
from __future__ import annotations

import re

import pytest

from sandbox_mcp.runner import SandboxRunRequest, run_sandbox, share_sandbox_file


pytestmark = pytest.mark.integration


def _assert_ok(output: str) -> None:
    assert "exit_code: 0" in output, output


def test_tool_agent_workflow_git_pip_pytest(bridge_dirs, monkeypatch, sandbox_image):
    monkeypatch.setenv("SANDBOX_IMAGE", sandbox_image)
    monkeypatch.setenv("SANDBOX_TIMEOUT", "120")
    out = run_sandbox(
        SandboxRunRequest(
            cmd=[
                "python3",
                "-u",
                "-c",
                r"""
from pathlib import Path
import subprocess, sys
repo = Path('/mnt/data/work/sampleproject-smoke')
if repo.exists():
    subprocess.run(['rm', '-rf', str(repo)], check=True)
clone = subprocess.run(['git', 'clone', '--depth', '1', 'https://github.com/pypa/sampleproject.git', str(repo)], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
print('clone_rc', clone.returncode)
install = subprocess.run([sys.executable, '-m', 'pip', 'install', '--user', '-q', '-e', str(repo), 'pytest'], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
print('install_rc', install.returncode)
test = subprocess.run([sys.executable, '-m', 'pytest', '-q', str(repo / 'tests')], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
print('pytest_rc', test.returncode)
print(test.stdout[-1000:])
""",
            ]
        )
    )

    _assert_ok(out)
    assert "clone_rc 0" in out
    assert "install_rc 0" in out
    assert "pytest_rc 0" in out


def test_tool_generates_and_shares_files(bridge_dirs, monkeypatch, sandbox_image):
    monkeypatch.setenv("SANDBOX_IMAGE", sandbox_image)
    out = run_sandbox(
        SandboxRunRequest(
            cmd=[
                "python3",
                "-u",
                "-c",
                "from pathlib import Path; Path('/mnt/data/_sandbox/smoke.json').write_text('{\"ok\": true}', encoding='utf-8')",
            ]
        )
    )

    _assert_ok(out)
    assert "shared_files_changed: smoke.json" in out
    meta = share_sandbox_file("smoke.json")
    assert meta["mime_type"] == "application/json"


def test_tool_conversion_binaries_smoke(bridge_dirs, monkeypatch, sandbox_image):
    monkeypatch.setenv("SANDBOX_IMAGE", sandbox_image)
    monkeypatch.setenv("SANDBOX_TIMEOUT", "120")
    out = run_sandbox(
        SandboxRunRequest(
            cmd=[
                "bash",
                "-lc",
                r"""
set -e
cat > /mnt/data/work/smoke.md <<'MD'
# Sandbox

ok
MD
pandoc /mnt/data/work/smoke.md -o /mnt/data/_sandbox/smoke.html
chromium --headless --no-sandbox --disable-gpu --print-to-pdf=/mnt/data/_sandbox/smoke.pdf file:///mnt/data/_sandbox/smoke.html >/tmp/chromium-pdf.log 2>&1
convert -size 64x64 xc:white -fill black -pointsize 20 -gravity center -annotate 0 OK /mnt/data/_sandbox/ocr.png
tesseract /mnt/data/_sandbox/ocr.png stdout > /mnt/data/_sandbox/ocr.txt
ffmpeg -hide_banner -loglevel error -f lavfi -i sine=frequency=1000:duration=0.1 -y /mnt/data/_sandbox/tone.wav
python3 - <<'PY'
from pathlib import Path
for name in ['smoke.pdf', 'ocr.png', 'ocr.txt', 'tone.wav']:
    p = Path('/mnt/data/_sandbox') / name
    print(name, p.exists(), p.stat().st_size if p.exists() else 0)
PY
""",
            ]
        )
    )

    _assert_ok(out)
    assert re.search(r"smoke\.pdf True [1-9]\d*", out), out
    assert re.search(r"tone\.wav True [1-9]\d*", out), out


def test_tool_chromium_headless_smoke(bridge_dirs, monkeypatch, sandbox_image):
    monkeypatch.setenv("SANDBOX_IMAGE", sandbox_image)
    monkeypatch.setenv("SANDBOX_TIMEOUT", "60")
    out = run_sandbox(
        SandboxRunRequest(
            cmd=[
                "bash",
                "-lc",
                "chromium --headless --no-sandbox --disable-gpu --dump-dom 'data:text/html,<title>Smoke</title><h1>ok</h1>' | head -20",
            ]
        )
    )

    _assert_ok(out)
    assert "<h1>ok</h1>" in out
