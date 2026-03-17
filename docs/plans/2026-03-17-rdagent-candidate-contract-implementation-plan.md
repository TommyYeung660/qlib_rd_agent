# RD-Agent Candidate Contract Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `qlib_rd_agent` emit and upload a scanner-friendly candidate artifact contract while preserving the legacy `discovered_factors.yaml` flow.

**Architecture:** Keep `discovered_factors.yaml` as the backward-compatible artifact, add `candidate_factors.yaml` as the canonical downstream artifact, and add `factor_manifest.json` as a metadata sidecar. The Dropbox upload layer publishes all three files, while CLI ergonomics remain unchanged.

**Tech Stack:** Python 3.10+, click, loguru, pathlib, json, pyyaml, pytest.

---

### Task 1: Add tests for dual artifact emission from factor collection

**Files:**
- Create: `tests/unit/test_qlib_runner_contract.py`
- Modify: `src/runner/qlib_runner.py`

**Step 1: Write the failing tests**

```python
def test_collect_factors_writes_discovered_candidate_and_manifest(tmp_path: Path) -> None:
    ...
```

Assert:

- `discovered_factors.yaml` exists
- `candidate_factors.yaml` exists
- `factor_manifest.json` exists
- candidate and discovered have the same `factors` payload
- manifest marks the stage as `candidate`

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_qlib_runner_contract.py -q`

Expected: FAIL because only `discovered_factors.yaml` exists today.

**Step 3: Write minimal implementation**

- Add helper(s) in `src/runner/qlib_runner.py` to write:
  - legacy YAML
  - candidate YAML
  - factor manifest JSON

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_qlib_runner_contract.py -q`

Expected: PASS.

### Task 2: Add upload tests for the expanded Dropbox artifact set

**Files:**
- Create: `tests/unit/test_dropbox_sync_contract.py`
- Modify: `src/bridge/dropbox_sync.py`

**Step 1: Write the failing tests**

```python
def test_upload_factors_uploads_candidate_manifest_and_legacy_yaml(tmp_path: Path) -> None:
    ...
```

Assert upload paths include:

- `/factors/discovered_factors.yaml`
- `/factors/candidate_factors.yaml`
- `/factors/factor_manifest.json`

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_dropbox_sync_contract.py -q`

Expected: FAIL because the uploader currently publishes only the legacy YAML.

**Step 3: Write minimal implementation**

- Expand `upload_factors()` so it uploads companion artifacts when present.
- Preserve legacy behavior if only `discovered_factors.yaml` exists.

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_dropbox_sync_contract.py -q`

Expected: PASS.

### Task 3: Update CLI docs and operator-facing README

**Files:**
- Modify: `README.md`

**Step 1: Update docs**

Document:

- the difference between `discovered_factors.yaml` and `candidate_factors.yaml`
- that scanner should ingest the candidate artifact
- that `factor_manifest.json` carries provenance

**Step 2: Run focused regression**

Run:
- `python -m pytest tests/unit/test_qlib_runner_contract.py tests/unit/test_dropbox_sync_contract.py -q`

Expected: PASS.

### Task 4: Run the verification set

**Files:**
- No code changes

**Step 1: Run verification**

Run:
- `python -m pytest tests/unit/test_qlib_runner_contract.py tests/unit/test_dropbox_sync_contract.py -q`

Expected: PASS.

**Step 2: Optional manual sanity path**

Run:

```bash
python -m src.main run
python -m src.main upload
```

Expected:

- workspace contains all three artifacts
- Dropbox upload stage attempts to publish all three files

Plan complete and saved to `docs/plans/2026-03-17-rdagent-candidate-contract-implementation-plan.md`. Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?
