# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

import os
import sys
from typing import Any


# Prepare project imports
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from API import llm_api


# Print available models
def _print_available_models(engine: str) -> bool:
    """Print currently available models for the selected engine."""

    print(f"\n[1] Checking currently downloaded models in {engine}...")

    try:
        models = llm_api.get_models(engine)
    except Exception as exc:
        print(f"Error getting models: {exc}")
        return False

    print(f"  Found {len(models)} models:")
    for model in models:
        if isinstance(model, dict):
            print(f"  - {model.get('model')}")
        else:
            print(f"  - {model}")

    return True

# Print download progress
def _stream_download(engine: str, model_name: str) -> bool:
    """Download a model and print progress updates."""

    print(f"\n[2] Attempting to pull '{model_name}'...")

    try:
        progress_iterator = llm_api.download_model(engine, model_name, stream=True)

        # Stream progress updates as Ollama reports them.
        for chunk in progress_iterator:
            status = chunk.get("status", "")
            completed = chunk.get("completed") or 0
            total = chunk.get("total") or 0

            if total > 0 and "downloading" in status.lower():
                percent = (completed / total) * 100
                print(f"\r  Progress: {percent:.1f}% ({status})", end="", flush=True)
            else:
                print(f"\r  Status: {status}".ljust(50), end="", flush=True)

        print("\n\n  [OK] Download complete!")
        return True
    except Exception as exc:
        print(f"\n  [ERROR] Error downloading model: {exc}")
        return False

# Extract generation content
def _extract_generation_content(response: Any) -> str | None:
    """Return visible text from a generation response payload."""

    if isinstance(response, dict):
        return response.get("message", {}).get("content") or response.get("response")

    message = getattr(response, "message", None)
    return getattr(message, "content", None) or getattr(response, "response", None)

# Test generation request
def _test_generation(engine: str, model_name: str) -> None:
    """Send a simple generation request to the selected model."""

    print(f"\n[3] Testing simple generation with '{model_name}'...")

    try:
        response = llm_api.generate(
            engine=engine,
            model_name=model_name,
            messages=[{"role": "user", "content": "Reply with exactly 'Download Test OK'."}],
            stream=False,
        )
        print(f"  Response: {_extract_generation_content(response)}")
    except Exception as exc:
        print(f"  [ERROR] Error generating response: {exc}")


# Run download test
def run() -> None:
    """Download a test model and verify a simple generation request."""

    engine = "ollama-service"
    model_name = "gpt-oss:20b"

    print("Testing Model Download via llm_api...")

    if not _print_available_models(engine):
        return

    if not _stream_download(engine, model_name):
        return

    _test_generation(engine, model_name)


if __name__ == "__main__":
    run()
