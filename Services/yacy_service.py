# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

import os
import shutil
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen, urlretrieve

from Settings import settings

BASE_DIR = Path(__file__).resolve().parent.parent
YACY_SERVICE_DIR = BASE_DIR / "Tools" / "mcp-web-search" / "services" / "yacy"
YACY_RUNTIME_DIR = YACY_SERVICE_DIR / "runtime"
YACY_URL = "http://127.0.0.1:8090"
YACY_DOWNLOAD_URL = "https://release.yacy.net/yacy_latest.tar.gz"

_STARTED_BY_ASLM = False

_CONFIG_OVERRIDES = {
    "remotesearch.maxcount": "remotesearch.maxcount=12",
    "remotesearch.maxtime": "remotesearch.maxtime=2500",
    "cluster.mode": "cluster.mode=junior",
    "network.unit.domain": "network.unit.domain=global",
    "network.unit.dht": "network.unit.dht=true",
    "allowReceiveIndex.search": "allowReceiveIndex.search=true",
    "allowDistributeIndex": "allowDistributeIndex=false",
    "allowReceiveIndex": "allowReceiveIndex=false",
    "federated.service.solr.indexing.writeEnabled": "federated.service.solr.indexing.writeEnabled=false",
    "50_localcrawl_isPaused": "50_localcrawl_isPaused=true",
    "60_remotecrawlloader_isPaused": "60_remotecrawlloader_isPaused=true",
    "62_remotetriggeredcrawl_isPaused": "62_remotetriggeredcrawl_isPaused=true",
    "crawler.MaxActiveThreads": "crawler.MaxActiveThreads=16",
    "crawler.MaxSameHostInQueue": "crawler.MaxSameHostInQueue=8",
    "indexer.slots": "indexer.slots=8",
    "stacker.slots": "stacker.slots=256",
    "crawler.latencyFactor": "crawler.latencyFactor=1.5",
    "50_localcrawl_idlesleep": "50_localcrawl_idlesleep=10000",
    "50_localcrawl_busysleep": "50_localcrawl_busysleep=5000",
    "60_remotecrawlloader_busysleep": "60_remotecrawlloader_busysleep=5000",
    "50_localcrawl_loadprereq": "50_localcrawl_loadprereq=64.0",
    "javastart_Xmx": "javastart_Xmx=Xmx1280m",
    "javastart_priority": "javastart_priority=20",
}


def _log(message: str, log: bool) -> None:
    """Print a YaCy service log line when verbose output is enabled."""

    if log:
        print(f"[ASLM-Chat] {message}")


def _warn(message: str) -> None:
    """Print a YaCy warning message."""

    print(f"[ASLM-Chat] Warning: {message}")


def is_enabled() -> bool:
    """Return whether YaCy is enabled in ASLM settings."""

    return bool(settings.get("use-yacy", False))


def _is_ready(timeout: float = 1.5) -> bool:
    """Return whether the local YaCy HTTP endpoint is already responding."""

    try:
        with urlopen(f"{YACY_URL}/", timeout=timeout) as response:
            return response.status < 500
    except (OSError, URLError):
        return False


def _wait_until_ready(timeout_seconds: float = 45.0) -> bool:
    """Wait until YaCy starts serving HTTP requests."""

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if _is_ready():
            return True
        time.sleep(0.5)
    return False


def _start_script() -> Path | None:
    """Return the platform-specific YaCy start script when available."""

    candidates = ("startYACY.bat", "startYACY.sh") if os.name == "nt" else ("startYACY.sh", "startYACY.bat")
    for name in candidates:
        path = YACY_RUNTIME_DIR / name
        if path.exists():
            return path
    return None


def _stop_script() -> Path | None:
    """Return the platform-specific YaCy stop script when available."""

    candidates = ("stopYACY.bat", "stopYACY.sh") if os.name == "nt" else ("stopYACY.sh", "stopYACY.bat")
    for name in candidates:
        path = YACY_RUNTIME_DIR / name
        if path.exists():
            return path
    return None


def _locate_extracted_root(root: Path) -> Path | None:
    """Find the extracted YaCy application root containing a start script."""

    for script_name in ("startYACY.bat", "startYACY.sh"):
        for candidate in root.rglob(script_name):
            return candidate.parent
    return None


def _safe_extract(archive: tarfile.TarFile, destination: Path) -> None:
    """Safely extract a tar archive into the requested destination."""

    destination_root = destination.resolve()
    for member in archive.getmembers():
        member_path = (destination / member.name).resolve()
        if not member_path.is_relative_to(destination_root):
            raise ValueError(f"Archive member escapes destination: {member.name}")
    archive.extractall(destination)


def _configure_yacy(log: bool) -> None:
    """Apply the low-resource YaCy configuration used by ASLM-Chat."""

    settings_dir = YACY_RUNTIME_DIR / "DATA" / "SETTINGS"
    settings_dir.mkdir(parents=True, exist_ok=True)
    conf_path = settings_dir / "yacy.conf"
    defaults_path = YACY_RUNTIME_DIR / "defaults" / "yacy.init"

    if not conf_path.exists() and defaults_path.exists():
        shutil.copyfile(defaults_path, conf_path)

    lines: list[str] = []
    if conf_path.exists():
        lines = conf_path.read_text(encoding="utf-8", errors="replace").splitlines()

    updated_lines = list(lines)
    for key, value in _CONFIG_OVERRIDES.items():
        prefix = f"{key}="
        for index, line in enumerate(updated_lines):
            if line.startswith(prefix):
                updated_lines[index] = value
                break
        else:
            updated_lines.append(value)

    conf_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
    _log(f"YaCy configuration applied at: {conf_path}", log)


def ensure_installed(log: bool = False) -> bool:
    """Download and configure YaCy into the bundled runtime directory."""

    if _start_script() is not None:
        _configure_yacy(log)
        return True

    YACY_SERVICE_DIR.mkdir(parents=True, exist_ok=True)

    _log("Downloading YaCy runtime...", log)
    with tempfile.TemporaryDirectory(dir=YACY_SERVICE_DIR) as temp_dir:
        temp_root = Path(temp_dir)
        archive_path = temp_root / "yacy_latest.tar.gz"
        extract_dir = temp_root / "extract"
        extract_dir.mkdir(parents=True, exist_ok=True)

        try:
            urlretrieve(YACY_DOWNLOAD_URL, archive_path)
        except Exception as exc:
            _warn(f"Could not download YaCy from {YACY_DOWNLOAD_URL}: {exc}")
            return False

        try:
            with tarfile.open(archive_path, "r:gz") as archive:
                _safe_extract(archive, extract_dir)
        except Exception as exc:
            _warn(f"Could not extract the YaCy archive: {exc}")
            return False

        extracted_root = _locate_extracted_root(extract_dir)
        if extracted_root is None:
            _warn("Could not locate the extracted YaCy runtime files.")
            return False

        if YACY_RUNTIME_DIR.exists():
            shutil.rmtree(YACY_RUNTIME_DIR)

        shutil.copytree(extracted_root, YACY_RUNTIME_DIR)

    _configure_yacy(log)
    _log(f"YaCy runtime installed at: {YACY_RUNTIME_DIR}", log)
    return _start_script() is not None


def start_yacy(log: bool = False) -> bool:
    """Start YaCy when it is enabled in ASLM settings."""

    global _STARTED_BY_ASLM

    if not is_enabled():
        _log("YaCy is disabled in settings; skipping startup.", log)
        return False

    if _is_ready():
        _log("YaCy is already running.", log)
        return True

    if not ensure_installed(log=log):
        return False

    if shutil.which("java") is None:
        _warn("YaCy requires Java 11+ in PATH, but no Java runtime was found.")
        return False

    script = _start_script()
    if script is None:
        _warn("YaCy start script is missing after installation.")
        return False

    _log("Starting YaCy service...", log)
    try:
        if script.suffix.lower() == ".bat":
            subprocess.Popen(
                ["cmd", "/c", script.name],
                cwd=YACY_RUNTIME_DIR,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        else:
            subprocess.Popen(
                ["sh", script.name],
                cwd=YACY_RUNTIME_DIR,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except Exception as exc:
        _warn(f"Could not start YaCy: {exc}")
        return False

    if not _wait_until_ready():
        _warn("YaCy did not become ready in time after startup.")
        return False

    _STARTED_BY_ASLM = True
    _log("YaCy is ready.", log)
    return True


def stop_yacy(log: bool = False) -> None:
    """Stop YaCy when it was started by the current ASLM process."""

    global _STARTED_BY_ASLM

    if not _STARTED_BY_ASLM:
        return

    script = _stop_script()
    if script is None:
        _warn("YaCy stop script is missing; leaving the service running.")
        return

    _log("Stopping YaCy service...", log)
    try:
        if script.suffix.lower() == ".bat":
            subprocess.run(
                ["cmd", "/c", script.name],
                cwd=YACY_RUNTIME_DIR,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        else:
            subprocess.run(
                ["sh", script.name],
                cwd=YACY_RUNTIME_DIR,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except Exception as exc:
        _warn(f"Could not stop YaCy cleanly: {exc}")
    finally:
        _STARTED_BY_ASLM = False
