from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import dropbox
from dropbox.exceptions import ApiError, AuthError
from dropbox.files import WriteMode
from loguru import logger

# Dropbox API upload limit: 150 MB per single call
_UPLOAD_SIZE_LIMIT = 150 * 1024 * 1024


class DropboxClient:
    def __init__(self, token: str, refresh_token: str, app_key: str, app_secret: str):
        self.dbx = dropbox.Dropbox(
            oauth2_access_token=token,
            oauth2_refresh_token=refresh_token,
            app_key=app_key,
            app_secret=app_secret,
        )

    def upload_json(
        self, data: Dict[str, Any], filename: str, folder: str = ""
    ) -> bool:
        try:
            json_str = json.dumps(data, indent=2, ensure_ascii=False)
            json_bytes = json_str.encode("utf-8")
            path = f"{folder}/{filename}" if folder else f"/{filename}"
            path = path.replace("//", "/")
            logger.info("Uploading {} bytes to Dropbox: {}", len(json_bytes), path)
            self.dbx.files_upload(json_bytes, path, mode=WriteMode("overwrite"))
            logger.info("Upload successful!")
            return True
        except AuthError as e:
            logger.error("Dropbox authentication failed: {}", e)
            return False
        except ApiError as e:
            logger.error("Dropbox API error: {}", e)
            return False
        except Exception as e:
            logger.error("Unexpected error uploading to Dropbox: {}", e)
            return False

    def upload_file(self, local_path: Path, dropbox_path: str) -> bool:
        try:
            file_size = local_path.stat().st_size
            dropbox_path = dropbox_path.replace("//", "/")
            if file_size > _UPLOAD_SIZE_LIMIT:
                return self._upload_large_file(local_path, dropbox_path, file_size)
            with open(local_path, "rb") as f:
                self.dbx.files_upload(
                    f.read(), dropbox_path, mode=WriteMode("overwrite")
                )
            size_mb = file_size / (1024 * 1024)
            logger.info(
                "Uploaded {} ({:.1f} MB) -> {}", local_path.name, size_mb, dropbox_path
            )
            return True
        except AuthError as e:
            logger.error("Dropbox authentication failed: {}", e)
            return False
        except ApiError as e:
            logger.error("Dropbox API error uploading {}: {}", local_path.name, e)
            return False
        except Exception as e:
            logger.error("Unexpected error uploading {}: {}", local_path.name, e)
            return False

    def _upload_large_file(
        self, local_path: Path, dropbox_path: str, file_size: int
    ) -> bool:
        chunk_size = 8 * 1024 * 1024
        try:
            with open(local_path, "rb") as f:
                session = self.dbx.files_upload_session_start(f.read(chunk_size))
                cursor = dropbox.files.UploadSessionCursor(
                    session_id=session.session_id, offset=f.tell()
                )
                commit = dropbox.files.CommitInfo(
                    path=dropbox_path, mode=WriteMode("overwrite")
                )
                while f.tell() < file_size:
                    remaining = file_size - f.tell()
                    if remaining <= chunk_size:
                        self.dbx.files_upload_session_finish(
                            f.read(remaining), cursor, commit
                        )
                    else:
                        self.dbx.files_upload_session_append_v2(
                            f.read(chunk_size), cursor
                        )
                        cursor.offset = f.tell()
            size_mb = file_size / (1024 * 1024)
            logger.info(
                "Uploaded large file {} ({:.1f} MB) -> {}",
                local_path.name,
                size_mb,
                dropbox_path,
            )
            return True
        except Exception as e:
            logger.error("Failed to upload large file {}: {}", local_path.name, e)
            return False

    def upload_directory(self, local_dir: Path, dropbox_folder: str) -> Dict[str, bool]:
        results: Dict[str, bool] = {}
        if not local_dir.exists():
            logger.error("Local directory not found: {}", local_dir)
            return results
        files = sorted(f for f in local_dir.rglob("*") if f.is_file())
        logger.info(
            "Uploading {} files from {} to Dropbox:{}",
            len(files),
            local_dir,
            dropbox_folder,
        )
        for file_path in files:
            rel_path = file_path.relative_to(local_dir)
            dbx_path = f"{dropbox_folder}/{rel_path}".replace("\\", "/")
            dbx_path = dbx_path.replace("//", "/")
            success = self.upload_file(file_path, dbx_path)
            results[str(rel_path)] = success
        succeeded = sum(1 for v in results.values() if v)
        failed = len(results) - succeeded
        logger.info(
            "Directory upload complete: {} succeeded, {} failed", succeeded, failed
        )
        return results

    def download_file(self, dropbox_path: str, local_path: Path) -> bool:
        try:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            dropbox_path = dropbox_path.replace("//", "/")
            self.dbx.files_download_to_file(str(local_path), dropbox_path)
            size_mb = local_path.stat().st_size / (1024 * 1024)
            logger.info(
                "Downloaded {} -> {} ({:.1f} MB)",
                dropbox_path,
                local_path,
                size_mb,
            )
            return True
        except ApiError as e:
            if e.error.is_path() and e.error.get_path().is_not_found():
                logger.warning("File not found on Dropbox: {}", dropbox_path)
            else:
                logger.error("Dropbox API error downloading {}: {}", dropbox_path, e)
            return False
        except Exception as e:
            logger.error("Unexpected error downloading {}: {}", dropbox_path, e)
            return False

    def download_directory(
        self, dropbox_folder: str, local_dir: Path
    ) -> Dict[str, bool]:
        results: Dict[str, bool] = {}
        try:
            entries = self._list_folder_recursive(dropbox_folder)
        except Exception as e:
            logger.error("Failed to list Dropbox folder {}: {}", dropbox_folder, e)
            return results
        logger.info(
            "Downloading {} files from Dropbox:{} to {}",
            len(entries),
            dropbox_folder,
            local_dir,
        )
        for entry in entries:
            if not isinstance(entry, dropbox.files.FileMetadata):
                continue
            rel_path = entry.path_display[len(dropbox_folder) :].lstrip("/")
            local_path = local_dir / rel_path
            success = self.download_file(entry.path_display, local_path)
            results[rel_path] = success
        succeeded = sum(1 for v in results.values() if v)
        failed = len(results) - succeeded
        logger.info(
            "Directory download complete: {} succeeded, {} failed", succeeded, failed
        )
        return results

    def _list_folder_recursive(
        self, dropbox_folder: str
    ) -> List[dropbox.files.FileMetadata]:
        entries: List[dropbox.files.FileMetadata] = []
        try:
            result = self.dbx.files_list_folder(dropbox_folder, recursive=True)
            entries.extend(
                e for e in result.entries if isinstance(e, dropbox.files.FileMetadata)
            )
            while result.has_more:
                result = self.dbx.files_list_folder_continue(result.cursor)
                entries.extend(
                    e
                    for e in result.entries
                    if isinstance(e, dropbox.files.FileMetadata)
                )
        except ApiError as e:
            if e.error.is_path() and e.error.get_path().is_not_found():
                logger.info("Dropbox folder not found: {}", dropbox_folder)
            else:
                raise
        return entries

    def list_folder(self, dropbox_folder: str) -> List[str]:
        try:
            result = self.dbx.files_list_folder(dropbox_folder)
            return [e.name for e in result.entries]
        except ApiError:
            return []
