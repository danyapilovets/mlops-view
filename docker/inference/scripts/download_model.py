#!/usr/bin/env python3
"""Download model weights from GCS (gs://) or Hugging Face Hub to a local directory."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import urlparse

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Download model from GCS or Hugging Face Hub")
    p.add_argument("--source", required=True, help="gs://bucket/prefix or Hugging Face repo id")
    p.add_argument("--output-dir", required=True, type=Path, help="Local directory for weights")
    p.add_argument(
        "--revision",
        default=None,
        help="Optional HF revision (branch, tag, or commit); ignored for GCS",
    )
    return p.parse_args()


def _download_gcs(gs_uri: str, output_dir: Path) -> None:
    from google.cloud import storage
    from google.cloud.exceptions import GoogleCloudError

    parsed = urlparse(gs_uri)
    if parsed.scheme != "gs" or not parsed.netloc:
        raise ValueError(f"Invalid GCS URI: {gs_uri}")

    bucket_name = parsed.netloc
    prefix = (parsed.path or "").lstrip("/")

    output_dir.mkdir(parents=True, exist_ok=True)
    client = storage.Client()
    bucket = client.bucket(bucket_name)

    blobs: Iterable = list(bucket.list_blobs(prefix=prefix if prefix else None))
    files = [b for b in blobs if not b.name.endswith("/")]
    if not files:
        raise FileNotFoundError(
            f"No objects found under gs://{bucket_name}/{prefix}".rstrip("/"),
        )

    for blob in files:
        rel = blob.name[len(prefix) :].lstrip("/") if prefix else blob.name
        dest = output_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            logger.info("Downloading gs://%s/%s -> %s", bucket_name, blob.name, dest)
            blob.download_to_filename(str(dest))
        except GoogleCloudError as e:
            logger.exception("GCS download failed for %s", blob.name)
            raise RuntimeError(f"Failed to download {blob.name}: {e}") from e


def _download_hf(repo_id: str, output_dir: Path, revision: str | None) -> None:
    from huggingface_hub import snapshot_download
    from huggingface_hub.utils import HfHubHTTPError

    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        path = snapshot_download(
            repo_id=repo_id,
            local_dir=str(output_dir),
            local_dir_use_symlinks=False,
            revision=revision,
        )
        logger.info("HF snapshot at %s", path)
    except HfHubHTTPError as e:
        logger.exception("Hugging Face download failed")
        raise RuntimeError(f"Hugging Face download failed: {e}") from e


def main() -> int:
    args = parse_args()
    source = args.source.strip()
    if not source:
        logger.error("--source must be non-empty")
        return 1

    try:
        if source.startswith("gs://"):
            _download_gcs(source, args.output_dir.resolve())
        else:
            _download_hf(source, args.output_dir.resolve(), args.revision)
    except Exception as e:
        logger.error("%s", e)
        return 1

    logger.info("Download complete: %s", args.output_dir.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
