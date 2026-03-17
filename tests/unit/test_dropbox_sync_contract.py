from __future__ import annotations

import json
from pathlib import Path

from src.bridge.dropbox_sync import upload_factors
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
