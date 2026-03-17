from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from src.config import AppConfig, DropboxConfig, LLMConfig, RDAgentConfig
from src.main import cli


def test_full_uploads_latest_run_log_and_immutable_archive(monkeypatch, tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    local_factors_dir = tmp_path / "factors"
    uploaded: dict[str, list] = {"run_log": [], "run_archive": []}

    monkeypatch.setattr(
        "src.main.load_config",
        lambda: AppConfig(
            dropbox=DropboxConfig(
                remote_rdagent_folder="/qlib_shared/rdagent_outputs",
                local_factors_dir=str(local_factors_dir),
            ),
            llm=LLMConfig(chat_model="openai/glm-4.7", embedding_model="litellm_proxy/text-embedding-3-small"),
            rdagent=RDAgentConfig(workspace_dir=str(workspace_root), max_iterations=6),
        ),
    )

    def _fake_download_shared_data(config: AppConfig) -> Path:
        shared_dir = tmp_path / "shared"
        shared_dir.mkdir(exist_ok=True)
        return shared_dir

    def _fake_run_rdagent(config: AppConfig, **kwargs) -> Path:
        workspace = kwargs.get("workspace_dir", workspace_root / "20260317_231530")
        workspace.mkdir(parents=True, exist_ok=True)
        return workspace

    def _fake_collect_factors(workspace_dir: str, config: AppConfig | None = None) -> str:
        workspace = Path(workspace_dir)
        discovered = workspace / "discovered_factors.yaml"
        candidate = workspace / "candidate_factors.yaml"
        manifest = workspace / "factor_manifest.json"
        discovered.write_text("factors: []\n", encoding="utf-8")
        candidate.write_text("factors: []\n", encoding="utf-8")
        manifest.write_text(json.dumps({"stage": "candidate"}), encoding="utf-8")
        return str(discovered)

    monkeypatch.setattr("src.bridge.dropbox_sync.download_shared_data", _fake_download_shared_data)
    monkeypatch.setattr("src.runner.qlib_runner.run_rdagent", _fake_run_rdagent)
    monkeypatch.setattr("src.runner.qlib_runner.collect_factors", _fake_collect_factors)
    monkeypatch.setattr("src.bridge.dropbox_sync.upload_factors", lambda config, factors_path: None)
    monkeypatch.setattr(
        "src.bridge.dropbox_sync.upload_run_log",
        lambda config, run_metadata: uploaded["run_log"].append(run_metadata),
    )
    monkeypatch.setattr(
        "src.bridge.dropbox_sync.upload_run_archive",
        lambda config, archive_dir, run_id: uploaded["run_archive"].append((Path(archive_dir), run_id)),
    )

    result = CliRunner().invoke(cli, ["full"])

    assert result.exit_code == 0
    assert len(uploaded["run_log"]) == 1
    assert len(uploaded["run_archive"]) == 1
    run_metadata = uploaded["run_log"][0]
    archive_dir, run_id = uploaded["run_archive"][0]
    assert run_metadata["run_id"] == run_id
    assert archive_dir.exists()
