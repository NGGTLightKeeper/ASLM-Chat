# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

import os
import tarfile

from huggingface_hub import HfApi


# Authentication settings.
TOKEN = os.environ.get("HF_TOKEN")
if not TOKEN:
    raise ValueError("Set the HF_TOKEN environment variable before running this script.")


# Dataset publishing.
def upload() -> None:
    """Archive the DATA directory and upload it to a dataset repository."""

    api = HfApi(token=TOKEN)

    # Resolve the current user namespace and dataset target.
    user_info = api.whoami()
    username = user_info["name"]
    repo_id = f"{username}/yacy-tech-docs"

    print(f"User: {username}")
    print(f"Repository: {repo_id}")

    try:
        api.create_repo(repo_id=repo_id, repo_type="dataset", private=False)
        print("Created a new dataset repository.")
    except Exception as error:
        print("Repository already exists or could not be created:", error)

    # Create the archive once and reuse it on repeated uploads.
    tar_filename = "yacy-db.tar.gz"
    if not os.path.exists(tar_filename):
        print(f"Archiving the DATA directory into {tar_filename}...")
        with tarfile.open(tar_filename, "w:gz") as tar:
            tar.add("DATA", arcname="DATA")
        print("Archive created.")
    else:
        print(f"Archive {tar_filename} already exists. Reusing it for upload.")

    # Upload the archive into the dataset repository.
    print("Uploading the file. This may take some time...")
    api.upload_file(
        path_or_fileobj=tar_filename,
        path_in_repo="db.tar.gz",
        repo_id=repo_id,
        repo_type="dataset",
    )
    print("Upload completed successfully.")


# Script entry point.
if __name__ == "__main__":
    upload()
