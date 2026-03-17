from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import yaml

from src.config import AppConfig, LLMConfig, RDAgentConfig
from src.runner.qlib_runner import (
    _build_stream_capture_mode,
    _format_run_metadata,
    _initialize_run_archive,
    _record_stream_line,
    _write_run_artifacts_index,
    collect_factors,
)


def test_collect_factors_writes_discovered_candidate_and_manifest(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "factor_example.py").write_text(
        '\n'.join(
            [
                '"""Momentum factor"""',
                'name = "FX_MOM_10"',
                'expression = "$close / Ref($close, 10) - 1"',
            ]
        ),
        encoding="utf-8",
    )

    discovered_path = collect_factors(
        str(workspace),
        config=AppConfig(
            llm=LLMConfig(chat_model="openai/glm-4.7", embedding_model="litellm_proxy/text-embedding-3-small"),
            rdagent=RDAgentConfig(max_iterations=8),
        ),
    )

    assert discovered_path == str(workspace / "discovered_factors.yaml")

    with open(workspace / "discovered_factors.yaml", "r", encoding="utf-8") as fh:
        discovered = yaml.safe_load(fh)
    with open(workspace / "candidate_factors.yaml", "r", encoding="utf-8") as fh:
        candidate = yaml.safe_load(fh)
    manifest = json.loads((workspace / "factor_manifest.json").read_text(encoding="utf-8"))

    assert discovered["factors"] == candidate["factors"]
    assert candidate["factors"][0]["name"] == "FX_MOM_10"
    assert manifest["stage"] == "candidate"
    assert manifest["generator"] == "qlib_rd_agent"
    assert manifest["factor_count"] == 1
    assert manifest["legacy_artifact"] == "discovered_factors.yaml"
    assert manifest["candidate_artifact"] == "candidate_factors.yaml"
    assert manifest["chat_model"] == "openai/glm-4.7"
    assert manifest["max_iterations"] == 8


def test_run_archive_helpers_write_raw_logs_events_and_artifact_index(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    run_id = "2026-03-17T23-15-30Z"

    archive = _initialize_run_archive(workspace, run_id)
    stream_counts = {"stdout": 0, "stderr": 0}

    _record_stream_line(
        archive,
        stream_name="stdout",
        line="factor generation started\n",
        run_id=run_id,
        workspace_dir=str(workspace),
        stream_counts=stream_counts,
        step="rdagent",
    )
    _record_stream_line(
        archive,
        stream_name="stderr",
        line="warning: fallback path used\n",
        run_id=run_id,
        workspace_dir=str(workspace),
        stream_counts=stream_counts,
        step="rdagent",
    )

    artifacts_path = _write_run_artifacts_index(
        workspace_dir=workspace,
        run_id=run_id,
        archive_paths=archive,
        upload_results={"stdout.raw.log": True, "stderr.raw.log": False},
    )

    metadata = _format_run_metadata(
        config=AppConfig(),
        start_time=datetime(2026, 3, 17, 23, 15, 30),
        end_time=datetime(2026, 3, 17, 23, 16, 0),
        return_code=0,
        workspace_dir=str(workspace),
        factors_path=None,
        run_id=run_id,
        archive_paths=archive,
        stream_counts=stream_counts,
        log_capture_complete=True,
    )

    assert archive["stdout"].read_text(encoding="utf-8") == "factor generation started\n"
    assert archive["stderr"].read_text(encoding="utf-8") == "warning: fallback path used\n"
    assert archive["console"].read_text(encoding="utf-8") == (
        "factor generation started\nwarning: fallback path used\n"
    )

    events = [
        json.loads(line)
        for line in archive["events"].read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [event["event"] for event in events] == [
        "rdagent_stdout_line",
        "rdagent_stderr_line",
    ]
    assert events[1]["data"]["stream_name"] == "stderr"

    artifacts = json.loads(artifacts_path.read_text(encoding="utf-8"))
    artifact_names = {artifact["name"] for artifact in artifacts["artifacts"]}
    assert {
        "stdout.raw.log",
        "stderr.raw.log",
        "console.raw.log",
        "events.jsonl",
        "run_artifacts.json",
    }.issubset(artifact_names)
    assert metadata["run_id"] == run_id
    assert metadata["stdout_line_count"] == 1
    assert metadata["stderr_line_count"] == 1
    assert metadata["stderr_nonempty"] is True
    assert metadata["log_capture_complete"] is True


def test_build_stream_capture_mode_prefers_pty_on_posix() -> None:
    assert _build_stream_capture_mode("posix") == "pty"
    assert _build_stream_capture_mode("nt") == "pipe"
