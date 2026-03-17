from __future__ import annotations

import json
from pathlib import Path

from src.bridge.dropbox_sync import (
    check_remote_data_freshness,
    upload_factors,
    upload_run_archive,
)
from src.config import AppConfig, DropboxConfig


class _FakeDropboxClient:
    def __init__(self) -> None:
        self.uploads: list[tuple[str, str]] = []

    def upload_file(self, local_path: Path, dropbox_path: str) -> bool:
        self.uploads.append((str(local_path), dropbox_path))
        return True


def test_upload_factors_uploads_candidate_manifest_and_legacy_yaml(monkeypatch, tmp_path: Path) -> None:
    discovered = tmp_path / "discovered_factors.yaml"
    candidate = tmp_path / "candidate_factors.yaml"
    manifest = tmp_path / "factor_manifest.json"

    discovered.write_text("factors: []\n", encoding="utf-8")
    candidate.write_text("factors: []\n", encoding="utf-8")
    manifest.write_text(json.dumps({"stage": "candidate"}), encoding="utf-8")

    fake_client = _FakeDropboxClient()
    monkeypatch.setattr("src.bridge.dropbox_sync._create_dropbox_client", lambda config: fake_client)

    config = AppConfig(
        dropbox=DropboxConfig(remote_rdagent_folder="/qlib_shared/rdagent_outputs")
    )
    upload_factors(config, str(discovered))

    remote_paths = [remote for _, remote in fake_client.uploads]
    assert "/qlib_shared/rdagent_outputs/factors/discovered_factors.yaml" in remote_paths
    assert "/qlib_shared/rdagent_outputs/factors/candidate_factors.yaml" in remote_paths
    assert "/qlib_shared/rdagent_outputs/factors/factor_manifest.json" in remote_paths


def test_upload_factors_keeps_legacy_behavior_when_only_discovered_exists(monkeypatch, tmp_path: Path) -> None:
    discovered = tmp_path / "discovered_factors.yaml"
    discovered.write_text("factors: []\n", encoding="utf-8")

    fake_client = _FakeDropboxClient()
    monkeypatch.setattr("src.bridge.dropbox_sync._create_dropbox_client", lambda config: fake_client)

    config = AppConfig(
        dropbox=DropboxConfig(remote_rdagent_folder="/qlib_shared/rdagent_outputs")
    )
    upload_factors(config, str(discovered))

    assert fake_client.uploads == [
        (
            str(discovered),
            "/qlib_shared/rdagent_outputs/factors/discovered_factors.yaml",
        )
    ]


def test_upload_run_archive_uploads_timestamped_run_batch(monkeypatch, tmp_path: Path) -> None:
    archive_dir = tmp_path / "2026-03-17T23-15-30Z"
    archive_dir.mkdir()
    for filename in [
        "run_metadata.json",
        "run_artifacts.json",
        "events.jsonl",
        "console.raw.log",
        "stdout.raw.log",
        "stderr.raw.log",
    ]:
        (archive_dir / filename).write_text("sample\n", encoding="utf-8")

    fake_client = _FakeDropboxClient()
    monkeypatch.setattr("src.bridge.dropbox_sync._create_dropbox_client", lambda config: fake_client)

    config = AppConfig(
        dropbox=DropboxConfig(remote_rdagent_folder="/qlib_shared/rdagent_outputs")
    )
    upload_run_archive(config, archive_dir, "2026-03-17T23-15-30Z")

    remote_paths = [remote for _, remote in fake_client.uploads]
    assert "/qlib_shared/rdagent_outputs/runs/2026-03-17T23-15-30Z/run_metadata.json" in remote_paths
    assert "/qlib_shared/rdagent_outputs/runs/2026-03-17T23-15-30Z/run_artifacts.json" in remote_paths
    assert "/qlib_shared/rdagent_outputs/runs/2026-03-17T23-15-30Z/events.jsonl" in remote_paths
    assert "/qlib_shared/rdagent_outputs/runs/2026-03-17T23-15-30Z/console.raw.log" in remote_paths
    assert "/qlib_shared/rdagent_outputs/runs/2026-03-17T23-15-30Z/stdout.raw.log" in remote_paths
    assert "/qlib_shared/rdagent_outputs/runs/2026-03-17T23-15-30Z/stderr.raw.log" in remote_paths


def test_check_remote_data_freshness_accepts_utc_z_suffix(monkeypatch, tmp_path: Path) -> None:
    local_dir = tmp_path / "shared_import"
    workspace_dir = tmp_path / "workspace"
    local_dir.mkdir()
    workspace_dir.mkdir()

    (local_dir / "manifest.json").write_text(
        json.dumps({"exported_at": "2026-02-10T09:00:24.617451Z"}),
        encoding="utf-8",
    )

    class _FakeManifestClient:
        def download_file(self, dropbox_path: str, local_path: Path) -> bool:
            local_path.write_text(
                json.dumps({"exported_at": "2026-02-10T09:00:25.617451Z"}),
                encoding="utf-8",
            )
            return True

    monkeypatch.setattr(
        "src.bridge.dropbox_sync._create_dropbox_client",
        lambda config: _FakeManifestClient(),
    )

    config = AppConfig(
        dropbox=DropboxConfig(local_download_dir=str(local_dir)),
    )
    config.rdagent.workspace_dir = str(workspace_dir)

    remote_manifest = check_remote_data_freshness(config)

    assert remote_manifest is not None
    assert remote_manifest["exported_at"] == "2026-02-10T09:00:25.617451Z"
