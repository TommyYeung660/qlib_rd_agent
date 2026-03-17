from __future__ import annotations

import json
from pathlib import Path

import yaml

from src.config import AppConfig, LLMConfig, RDAgentConfig
from src.runner.qlib_runner import collect_factors


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
