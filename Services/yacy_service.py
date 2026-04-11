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
YACY_DB_REPO_ID = "di74975/yacy-tech-docs"
YACY_DB_FILENAME = "db.tar.gz"

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


# Print verbose YaCy service output
def _log(message: str, log: bool) -> None:
    """Print a YaCy service message when verbose output is enabled."""

    if log:
        print(f"[ASLM-Chat] {message}")


# Print warning output
def _warn(message: str) -> None:
    """Print a YaCy warning message."""

    print(f"[ASLM-Chat] Warning: {message}")


# Read YaCy feature flag
def is_enabled() -> bool:
    """Return whether YaCy is enabled in settings."""

    return bool(settings.get("use-yacy", False))


# Check local YaCy readiness
def _is_ready(timeout: float = 1.5) -> bool:
    """Return whether the local YaCy HTTP endpoint is responding."""

    try:
        with urlopen(f"{YACY_URL}/", timeout=timeout) as response:
            return response.status < 500
    except (OSError, URLError):
        return False


# Wait for local YaCy readiness
def _wait_until_ready(timeout_seconds: float = 45.0) -> bool:
    """Wait until YaCy starts serving HTTP requests."""

    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        if _is_ready():
            return True

        time.sleep(0.5)

    return False


# Resolve YaCy start script
def _start_script() -> Path | None:
    """Return the platform-specific YaCy start script when available."""

    candidates = ("startYACY.bat", "startYACY.sh") if os.name == "nt" else ("startYACY.sh", "startYACY.bat")

    for name in candidates:
        path = YACY_RUNTIME_DIR / name
        if path.exists():
            return path

    return None


# Resolve YaCy stop script
def _stop_script() -> Path | None:
    """Return the platform-specific YaCy stop script when available."""

    candidates = ("stopYACY.bat", "stopYACY.sh") if os.name == "nt" else ("stopYACY.sh", "stopYACY.bat")

    for name in candidates:
        path = YACY_RUNTIME_DIR / name
        if path.exists():
            return path

    return None


# Find extracted YaCy root directory
def _locate_extracted_root(root: Path) -> Path | None:
    """Find the extracted YaCy application root containing a start script."""

    for script_name in ("startYACY.bat", "startYACY.sh"):
        for candidate in root.rglob(script_name):
            return candidate.parent

    return None


# Extract a tar archive safely
def _safe_extract(archive: tarfile.TarFile, destination: Path) -> None:
    """Safely extract a tar archive into the requested destination."""

    destination_root = destination.resolve()

    for member in archive.getmembers():
        member_path = (destination / member.name).resolve()
        if not member_path.is_relative_to(destination_root):
            raise ValueError(f"Archive member escapes destination: {member.name}")

    archive.extractall(destination)


# Apply managed YaCy configuration
def _configure_yacy(log: bool) -> None:
    """Apply the bundled low-resource YaCy configuration."""

    # Prepare config paths.
    settings_dir = YACY_RUNTIME_DIR / "DATA" / "SETTINGS"
    settings_dir.mkdir(parents=True, exist_ok=True)
    conf_path = settings_dir / "yacy.conf"
    defaults_path = YACY_RUNTIME_DIR / "defaults" / "yacy.init"

    # Bootstrap the runtime config from defaults when needed.
    if not conf_path.exists() and defaults_path.exists():
        shutil.copyfile(defaults_path, conf_path)

    # Read the current config so overrides can be merged in place.
    lines: list[str] = []
    if conf_path.exists():
        lines = conf_path.read_text(encoding="utf-8", errors="replace").splitlines()

    # Apply or append the managed override values.
    updated_lines = list(lines)
    for key, value in _CONFIG_OVERRIDES.items():
        prefix = f"{key}="
        for index, line in enumerate(updated_lines):
            if line.startswith(prefix):
                updated_lines[index] = value
                break
        else:
            updated_lines.append(value)

    # Persist the merged config back to disk.
    conf_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
    _log(f"YaCy configuration applied at: {conf_path}", log)


# Install bundled YaCy runtime
def ensure_installed(log: bool = False) -> bool:
    """Download and configure YaCy into the bundled runtime directory."""

    # Reuse the existing runtime when it is already present.
    if _start_script() is not None:
        _configure_yacy(log)
        return True

    # Prepare the service directory before downloading the runtime archive.
    YACY_SERVICE_DIR.mkdir(parents=True, exist_ok=True)

    _log("Downloading YaCy runtime...", log)
    with tempfile.TemporaryDirectory(dir=YACY_SERVICE_DIR) as temp_dir:
        temp_root = Path(temp_dir)
        archive_path = temp_root / "yacy_latest.tar.gz"
        extract_dir = temp_root / "extract"
        extract_dir.mkdir(parents=True, exist_ok=True)

        # Download the latest YaCy release archive.
        try:
            urlretrieve(YACY_DOWNLOAD_URL, archive_path)
        except Exception as exc:
            _warn(f"Could not download YaCy from {YACY_DOWNLOAD_URL}: {exc}")
            return False

        # Extract the downloaded archive into a temporary workspace.
        try:
            with tarfile.open(archive_path, "r:gz") as archive:
                _safe_extract(archive, extract_dir)
        except Exception as exc:
            _warn(f"Could not extract the YaCy archive: {exc}")
            return False

        # Locate the actual runtime root produced by the archive layout.
        extracted_root = _locate_extracted_root(extract_dir)
        if extracted_root is None:
            _warn("Could not locate the extracted YaCy runtime files.")
            return False

        # Replace the bundled runtime with the freshly extracted files.
        if YACY_RUNTIME_DIR.exists():
            shutil.rmtree(YACY_RUNTIME_DIR)

        shutil.copytree(extracted_root, YACY_RUNTIME_DIR)

    # Finalize the runtime with ASLM-managed configuration.
    _configure_yacy(log)
    _log(f"YaCy runtime installed at: {YACY_RUNTIME_DIR}", log)
    return _start_script() is not None


# Install bundled YaCy database snapshot
def ensure_database_snapshot(log: bool = False) -> bool:
    """Download and extract the optional YaCy database snapshot."""

    # Ensure the runtime exists before attempting to hydrate its data.
    if not ensure_installed(log=log):
        return False

    # Skip snapshot installation when runtime data already exists.
    data_dir = YACY_RUNTIME_DIR / "DATA"
    existing_entries = [
        entry for entry in data_dir.iterdir()
        if entry.name.upper() != "SETTINGS"
    ] if data_dir.exists() else []
    if existing_entries:
        _log(f"YaCy database snapshot already present in: {data_dir}", log)
        return True

    # Import the Hugging Face helper lazily because it is optional.
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        _warn(
            "Could not install YaCy database snapshot because "
            f"huggingface_hub is unavailable: {exc}"
        )
        return False

    _log("Downloading YaCy database snapshot from Hugging Face...", log)
    with tempfile.TemporaryDirectory(dir=YACY_SERVICE_DIR) as temp_dir:
        temp_root = Path(temp_dir)
        download_dir = temp_root / "downloads"
        download_dir.mkdir(parents=True, exist_ok=True)

        # Download the compressed snapshot archive into a temporary folder.
        try:
            archive_path = Path(
                hf_hub_download(
                    repo_id=YACY_DB_REPO_ID,
                    filename=YACY_DB_FILENAME,
                    repo_type="dataset",
                    local_dir=str(download_dir),
                )
            )
        except Exception as exc:
            _warn(f"Could not download the YaCy database snapshot: {exc}")
            return False

        # Extract the snapshot directly into the managed runtime.
        try:
            with tarfile.open(archive_path, "r:gz") as archive:
                _safe_extract(archive, YACY_RUNTIME_DIR)
        except Exception as exc:
            _warn(f"Could not extract the YaCy database snapshot: {exc}")
            return False

    _log(f"YaCy database snapshot installed into: {YACY_RUNTIME_DIR}", log)
    return True


# Start bundled YaCy service
def start_yacy(log: bool = False) -> bool:
    """Start YaCy when it is enabled in settings."""

    global _STARTED_BY_ASLM

    # Stop early when the feature is disabled.
    if not is_enabled():
        _log("YaCy is disabled in settings; skipping startup.", log)
        return False

    # Reuse the existing local service when it is already reachable.
    if _is_ready():
        _log("YaCy is already running.", log)
        return True

    # Ensure the runtime exists before launching the service.
    if not ensure_installed(log=log):
        return False

    # Validate the external Java dependency required by YaCy.
    if shutil.which("java") is None:
        _warn("YaCy requires Java 11+ in PATH, but no Java runtime was found.")
        return False

    # Resolve the platform-specific launch script.
    script = _start_script()
    if script is None:
        _warn("YaCy start script is missing after installation.")
        return False

    _log("Starting YaCy service...", log)
    try:
        # Use the native script for the current platform.
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

    # Wait until the HTTP endpoint is available before reporting success.
    if not _wait_until_ready():
        _warn("YaCy did not become ready in time after startup.")
        return False

    _STARTED_BY_ASLM = True
    _log("YaCy is ready.", log)
    return True


# Stop bundled YaCy service
def stop_yacy(log: bool = False) -> None:
    """Stop YaCy when it was started by the current ASLM process."""

    global _STARTED_BY_ASLM

    # Leave external YaCy instances untouched.
    if not _STARTED_BY_ASLM:
        return

    # Resolve the platform-specific stop script.
    script = _stop_script()
    if script is None:
        _warn("YaCy stop script is missing; leaving the service running.")
        return

    _log("Stopping YaCy service...", log)
    try:
        # Use the native stop command for the current platform.
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
