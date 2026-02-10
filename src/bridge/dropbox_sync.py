from __future__ import annotations

import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger

from src.config import AppConfig
from src.utils.dropbox_client import DropboxClient


def _create_dropbox_client(config: AppConfig) -> DropboxClient:
    """Create an authenticated DropboxClient from config."""
    return DropboxClient(
        token="",  # Access token optional when refresh token is provided
        refresh_token=config.dropbox.refresh_token,
        app_key=config.dropbox.app_key,
        app_secret=config.dropbox.app_secret,
    )


def _read_manifest(manifest_path: Path) -> Dict[str, Any]:
    """Read and parse a manifest.json file.

    Args:
        manifest_path: Path to the manifest.json file.

    Returns:
        Parsed manifest dictionary.

    Raises:
        FileNotFoundError: If the manifest file does not exist.
        json.JSONDecodeError: If the manifest file contains invalid JSON.
    """
    if not manifest_path.exists():
        raise FileNotFoundError("Manifest file not found: {}".format(manifest_path))

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    return manifest


def _log_manifest_summary(manifest: Dict[str, Any]) -> None:
    """Log a human-readable summary of a manifest dictionary.

    Args:
        manifest: Parsed manifest dictionary with keys like exported_at, symbol_count, date_range.
    """
    exported_at = manifest.get("exported_at", "unknown")
    symbol_count = manifest.get("symbol_count", "unknown")
    date_range = manifest.get("date_range", {})
    start = date_range.get("start", "unknown")
    end = date_range.get("end", "unknown")

    logger.info(
        "Manifest summary — exported_at: {}, symbols: {}, date_range: {} to {}",
        exported_at,
        symbol_count,
        start,
        end,
    )


def download_shared_data(config: AppConfig) -> Path:
    """Download scanner's shared export data from Dropbox.

    Downloads from config.dropbox.remote_shared_folder to config.dropbox.local_download_dir.
    Then extracts qlib_binary.zip into config.rdagent.qlib_data_path.

    Steps:
        1. Download all files from /qlib_shared/ to data/shared_import/
        2. Verify manifest.json exists
        3. Extract qlib_binary.zip to data/qlib/ (the qlib_data_path)
        4. Log summary of downloaded data

    Args:
        config: Application configuration.

    Returns:
        Path to the local download directory.

    Raises:
        FileNotFoundError: If manifest.json is missing after download.
    """
    client = _create_dropbox_client(config)

    local_dir = Path(config.dropbox.local_download_dir)
    local_dir.mkdir(parents=True, exist_ok=True)

    remote_folder = config.dropbox.remote_shared_folder
    logger.info(
        "Downloading shared data from Dropbox: {} -> {}", remote_folder, local_dir
    )
    client.download_directory(remote_folder, local_dir)

    # ------------------------------------------------------------------
    # Verify manifest.json
    # ------------------------------------------------------------------
    manifest_path = local_dir / "manifest.json"
    manifest = _read_manifest(manifest_path)
    _log_manifest_summary(manifest)

    # ------------------------------------------------------------------
    # Extract qlib_binary.zip into the configured qlib data directory
    # ------------------------------------------------------------------
    zip_path = local_dir / "qlib_binary.zip"
    if zip_path.exists():
        qlib_dir = Path(config.rdagent.qlib_data_path)

        if qlib_dir.exists():
            logger.info("Removing existing Qlib binary directory: {}", qlib_dir)
            shutil.rmtree(qlib_dir)

        qlib_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(qlib_dir)

        logger.info("Extracted Qlib binary data to {}", qlib_dir)
    else:
        logger.warning(
            "qlib_binary.zip not found in downloaded data; skipping extraction"
        )

    logger.info("Shared data download complete: {}", local_dir)
    return local_dir


def upload_factors(config: AppConfig, factors_yaml_path: str) -> None:
    """Upload discovered factors YAML to Dropbox.

    Uploads to config.dropbox.remote_rdagent_folder/factors/discovered_factors.yaml.

    Args:
        config: Application configuration.
        factors_yaml_path: Local path to the discovered_factors.yaml file.

    Raises:
        FileNotFoundError: If factors_yaml_path does not exist.
    """
    local_path = Path(factors_yaml_path)
    if not local_path.exists():
        raise FileNotFoundError("Factors YAML file not found: {}".format(local_path))

    client = _create_dropbox_client(config)

    remote_path = "{}/factors/discovered_factors.yaml".format(
        config.dropbox.remote_rdagent_folder
    )
    logger.info("Uploading factors YAML ({}) to Dropbox: {}", local_path, remote_path)
    client.upload_file(local_path, remote_path)

    logger.info("Uploaded factors to Dropbox: {}", remote_path)


def upload_run_log(config: AppConfig, run_metadata: Dict[str, Any]) -> None:
    """Upload RD-Agent run metadata to Dropbox as run_log.json.

    Creates a temporary JSON file in the workspace directory, uploads it to
    config.dropbox.remote_rdagent_folder/run_log.json, then cleans up the temp file.

    Args:
        config: Application configuration.
        run_metadata: Dictionary with run info (start_time, end_time, iterations, status, etc.)

    Raises:
        OSError: If the temporary file cannot be written.
    """
    client = _create_dropbox_client(config)

    workspace_dir = Path(config.rdagent.workspace_dir)
    workspace_dir.mkdir(parents=True, exist_ok=True)

    temp_path = workspace_dir / "run_log.json"
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(run_metadata, f, indent=2, default=str)

        remote_path = "{}/run_log.json".format(config.dropbox.remote_rdagent_folder)
        logger.info("Uploading run log to Dropbox: {}", remote_path)
        client.upload_file(temp_path, remote_path)

        logger.info("Uploaded run log to Dropbox")
    finally:
        if temp_path.exists():
            temp_path.unlink()
            logger.debug("Cleaned up temporary run log file: {}", temp_path)


def check_remote_data_freshness(config: AppConfig) -> Optional[Dict[str, Any]]:
    """Check if remote shared data is newer than local data.

    Reads local manifest.json and compares with a freshly-downloaded remote manifest.
    The comparison uses the ``exported_at`` ISO-8601 timestamp in each manifest.

    Args:
        config: Application configuration.

    Returns:
        Remote manifest dict if remote data is newer than local, None otherwise.
        Also returns the remote manifest if no local manifest exists yet.
    """
    client = _create_dropbox_client(config)

    local_dir = Path(config.dropbox.local_download_dir)
    local_manifest_path = local_dir / "manifest.json"

    # ------------------------------------------------------------------
    # Download remote manifest to a temp location
    # ------------------------------------------------------------------
    workspace_dir = Path(config.rdagent.workspace_dir)
    workspace_dir.mkdir(parents=True, exist_ok=True)
    remote_manifest_tmp = workspace_dir / "remote_manifest.json"

    remote_manifest_remote_path = "{}/manifest.json".format(
        config.dropbox.remote_shared_folder
    )
    try:
        client.download_file(remote_manifest_remote_path, remote_manifest_tmp)
    except FileNotFoundError:
        logger.warning(
            "Remote manifest.json not found at {}; cannot check freshness",
            remote_manifest_remote_path,
        )
        return None

    remote_manifest = _read_manifest(remote_manifest_tmp)

    # Clean up temp file
    if remote_manifest_tmp.exists():
        remote_manifest_tmp.unlink()

    # ------------------------------------------------------------------
    # If no local manifest exists, remote data is considered newer
    # ------------------------------------------------------------------
    if not local_manifest_path.exists():
        logger.info("No local manifest found; remote data is treated as newer")
        return remote_manifest

    local_manifest = _read_manifest(local_manifest_path)

    # ------------------------------------------------------------------
    # Compare exported_at timestamps
    # ------------------------------------------------------------------
    local_exported_at_str = local_manifest.get("exported_at")
    remote_exported_at_str = remote_manifest.get("exported_at")

    if not remote_exported_at_str:
        logger.warning(
            "Remote manifest missing 'exported_at'; cannot determine freshness"
        )
        return None

    if not local_exported_at_str:
        logger.info(
            "Local manifest missing 'exported_at'; remote data treated as newer"
        )
        return remote_manifest

    try:
        local_ts = datetime.fromisoformat(local_exported_at_str)
        remote_ts = datetime.fromisoformat(remote_exported_at_str)
    except ValueError as exc:
        logger.error("Failed to parse 'exported_at' timestamps: {}", exc)
        return None

    if remote_ts > local_ts:
        logger.info(
            "Remote data is newer (remote: {}, local: {})",
            remote_exported_at_str,
            local_exported_at_str,
        )
        return remote_manifest

    logger.info(
        "Local data is up-to-date (remote: {}, local: {})",
        remote_exported_at_str,
        local_exported_at_str,
    )
    return None
