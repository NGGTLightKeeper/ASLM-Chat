# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

import os
import tarfile
from pathlib import Path

from huggingface_hub import hf_hub_download


# Dataset location settings.
REPO_ID = "di74975/yacy-tech-docs"
FILENAME = "db.tar.gz"
INSTALL_DIR = Path("./")


# Archive extraction.
def download_and_extract() -> None:
    """Download the archive from Hugging Face and extract it locally."""

    data_dir = INSTALL_DIR / "DATA"
    if data_dir.exists() and any(data_dir.iterdir()):
        print(f"Directory {data_dir} already exists and is not empty. The database is already installed.")
        return

    # Download the dataset archive into a temporary local directory.
    print("Downloading the database archive from Hugging Face...")
    local_path = hf_hub_download(
        repo_id=REPO_ID,
        filename=FILENAME,
        repo_type="dataset",
        local_dir="./downloads",
    )

    # Extract only safe archive members to avoid path traversal.
    print(f"Extracting {local_path}...")
    INSTALL_DIR.mkdir(exist_ok=True)

    with tarfile.open(local_path, "r:gz") as tar:
        safe_members = [
            member
            for member in tar.getmembers()
            if not member.name.startswith("/") and ".." not in member.name
        ]
        tar.extractall(path=INSTALL_DIR, members=safe_members)

    # Remove temporary download artifacts after a successful extraction.
    os.remove(local_path)
    if os.path.exists("./downloads") and not os.listdir("./downloads"):
        os.rmdir("./downloads")

    print("Done. You can now run: docker compose up -d")


# Script entry point.
if __name__ == "__main__":
    download_and_extract()
