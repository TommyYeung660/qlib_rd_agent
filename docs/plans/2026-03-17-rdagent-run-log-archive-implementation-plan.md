# RD-Agent Run Log Archive Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add immutable per-run Dropbox log archives, raw stdout/stderr capture, and structured event logs to `qlib_rd_agent` without breaking the existing latest-only factor contract.

**Architecture:** The wrapper will generate a `run_id`, create per-run local archive artifacts in the workspace, tee subprocess stdout/stderr into raw log files while preserving live terminal visibility, and upload a timestamped Dropbox batch under `rdagent_outputs/runs/<run_id>/`. Existing `run_log.json` and factor uploads remain as compatibility pointers.

**Tech Stack:** Python 3.10, `loguru`, `subprocess`, `threading`, `json`, `pytest`

---

### Task 1: Add run archive contract tests

**Files:**
- Modify: `tests/unit/test_qlib_runner_contract.py`

**Step 1: Write the failing test**

Add a test that expects helper output for:

- `stdout.raw.log`
- `stderr.raw.log`
- `console.raw.log`
- `events.jsonl`
- `run_artifacts.json`

and verifies the returned metadata includes `stderr_nonempty` and line counts.

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_qlib_runner_contract.py -q`
Expected: FAIL because the archive helpers and metadata fields do not exist yet.

**Step 3: Write minimal implementation**

Add helper(s) in `src/runner/qlib_runner.py` to:

- build per-run archive paths
- write artifact index
- enrich run metadata with log counters

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_qlib_runner_contract.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/test_qlib_runner_contract.py src/runner/qlib_runner.py
git commit -m "test: add run archive contract coverage"
```

### Task 2: Add subprocess tee capture tests

**Files:**
- Modify: `tests/unit/test_qlib_runner_contract.py`

**Step 1: Write the failing test**

Add a test for a small fake subprocess reader flow asserting:

- stdout lines are written to `stdout.raw.log`
- stderr lines are written to `stderr.raw.log`
- both appear in `console.raw.log`
- event entries are emitted for stdout/stderr line handling

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_qlib_runner_contract.py -q`
Expected: FAIL because tee capture utilities do not exist yet.

**Step 3: Write minimal implementation**

Implement small capture helpers in `src/runner/qlib_runner.py` using:

- file handles
- a thread-safe event writer
- line counters

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_qlib_runner_contract.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/test_qlib_runner_contract.py src/runner/qlib_runner.py
git commit -m "feat: add raw subprocess tee capture"
```

### Task 3: Add Dropbox archive upload tests

**Files:**
- Modify: `tests/unit/test_dropbox_sync_contract.py`

**Step 1: Write the failing test**

Add tests asserting a new upload helper sends:

- `run_metadata.json`
- `run_artifacts.json`
- `events.jsonl`
- `console.raw.log`
- `stdout.raw.log`
- `stderr.raw.log`

to `/qlib_shared/rdagent_outputs/runs/<run_id>/...`

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_dropbox_sync_contract.py -q`
Expected: FAIL because no archive upload helper exists yet.

**Step 3: Write minimal implementation**

Implement archive batch upload support in `src/bridge/dropbox_sync.py`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_dropbox_sync_contract.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/test_dropbox_sync_contract.py src/bridge/dropbox_sync.py
git commit -m "feat: add Dropbox run archive upload"
```

### Task 4: Wire full pipeline archive behavior

**Files:**
- Modify: `src/main.py`
- Modify: `src/runner/qlib_runner.py`
- Modify: `src/bridge/dropbox_sync.py`

**Step 1: Write the failing test**

Add a test proving `full` uploads both:

- compatibility `run_log.json`
- immutable `runs/<run_id>/...` archive batch

and does so even when factors are absent or run status is failure-like.

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_qlib_runner_contract.py tests/unit/test_dropbox_sync_contract.py -q`
Expected: FAIL because the CLI and upload flow do not wire archive uploads yet.

**Step 3: Write minimal implementation**

Update the full pipeline to:

- create archive artifacts
- upload archive batch
- preserve existing factor upload and latest run log behavior

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_qlib_runner_contract.py tests/unit/test_dropbox_sync_contract.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/main.py src/runner/qlib_runner.py src/bridge/dropbox_sync.py tests/unit/test_qlib_runner_contract.py tests/unit/test_dropbox_sync_contract.py
git commit -m "feat: archive per-run RD-Agent logs"
```

### Task 5: Update operator documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/plans/2026-03-17-rdagent-run-log-archive-design.md`
- Create: `docs/integrations/2026-03-17-rdagent-run-log-archive-operator-notes.md`

**Step 1: Write the failing doc expectation**

Document the new Dropbox archive path and local workspace artifacts that operators should expect after a run.

**Step 2: Verify docs are missing required content**

Run: `rg -n "rdagent_outputs/runs|stderr.raw.log|events.jsonl" README.md docs`
Expected: missing or incomplete coverage

**Step 3: Write minimal documentation**

Add concise operator guidance for:

- per-run archive path
- raw stderr inspection
- compatibility files that still update

**Step 4: Verify docs now include required content**

Run: `rg -n "rdagent_outputs/runs|stderr.raw.log|events.jsonl" README.md docs`
Expected: matches in the updated docs

**Step 5: Commit**

```bash
git add README.md docs/integrations/2026-03-17-rdagent-run-log-archive-operator-notes.md docs/plans/2026-03-17-rdagent-run-log-archive-design.md
git commit -m "docs: add RD-Agent run archive operator notes"
```

### Task 6: Final verification

**Files:**
- Modify: none

**Step 1: Run focused tests**

Run:

```bash
pytest tests/unit/test_qlib_runner_contract.py tests/unit/test_dropbox_sync_contract.py -q
```

Expected: PASS

**Step 2: Run targeted grep verification**

Run:

```bash
rg -n "runs/<run_id>|stderr.raw.log|events.jsonl|run_artifacts.json" docs README.md src tests
```

Expected: matches across code, tests, and docs

**Step 3: Review git diff**

Run:

```bash
git diff --stat
```

Expected: only planned files changed

**Step 4: Commit**

```bash
git add README.md docs src tests
git commit -m "feat: add analyzable RD-Agent run log archives"
```
