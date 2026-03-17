# RD-Agent Run Log Archive Design

## Context

`qlib_rd_agent` currently provides:

- interactive terminal output via `loguru`
- per-run `workspace/<timestamp>/run_metadata.json`
- a latest-only Dropbox `run_log.json`

This is not sufficient for production diagnosis. Operators can watch a live run, but they cannot reliably inspect a completed run end-to-end, compare runs, or confirm whether stderr stayed quiet throughout a supposedly successful job.

For `v1.5.0`, the logging model must support:

- immutable per-run archives
- raw stderr retention without losing live terminal visibility
- machine-readable event timelines for later analysis
- Dropbox retention of every run, not just the latest summary

## Goals

- Preserve the current live operator experience during `python -m src.main full`
- Persist complete raw run output for each run
- Upload a complete, timestamped log batch to Dropbox for every run
- Keep existing latest-only compatibility files for current workflows
- Make failed runs just as diagnosable as successful runs

## Non-Goals

- Building a central database or analytics warehouse
- Parsing every RD-Agent output line into a semantic model
- Changing the scanner-facing factor contract
- Changing FX cadence, model settings, or Dropbox shared bundle layout

## Current Gaps

### Console output is not archived

`run_rdagent()` launches the RD-Agent subprocess with terminal-bound output. This is good for live observation but means the wrapper does not retain complete raw stdout/stderr artifacts.

### Dropbox only stores latest run metadata

`upload_run_log()` overwrites `run_log.json`. That preserves a latest pointer but destroys per-run history.

### Structured event history is missing

There is no event stream answering:

- when sync started and finished
- when data preparation started and failed
- when RD-Agent launched and exited
- which artifacts were written
- which uploads completed

## Recommended Architecture

Use a dual-layer logging model:

1. Immutable per-run archive
2. Latest compatibility pointers

### 1. Immutable per-run archive

Each invocation of `python -m src.main full` or `run` gets a `run_id` derived from UTC timestamp.

Local workspace example:

```text
workspace/20260317_231530/
  run_metadata.json
  run_artifacts.json
  events.jsonl
  console.raw.log
  stdout.raw.log
  stderr.raw.log
  discovered_factors.yaml
  candidate_factors.yaml
  factor_manifest.json
```

Dropbox archive example:

```text
/qlib_shared/rdagent_outputs/runs/2026-03-17T23-15-30Z/
  run_metadata.json
  run_artifacts.json
  events.jsonl
  console.raw.log
  stdout.raw.log
  stderr.raw.log
  discovered_factors.yaml
  candidate_factors.yaml
  factor_manifest.json
```

The archive is immutable. A new run always creates a new directory.

### 2. Latest compatibility pointers

Keep uploading:

- `/qlib_shared/rdagent_outputs/run_log.json`
- `/qlib_shared/rdagent_outputs/factors/discovered_factors.yaml`
- `/qlib_shared/rdagent_outputs/factors/candidate_factors.yaml`
- `/qlib_shared/rdagent_outputs/factors/factor_manifest.json`

This preserves existing operator and downstream assumptions while adding proper historical retention under `runs/<run_id>/`.

## Raw Output Capture Model

### Requirement

Operators must continue seeing live output in the terminal, especially stderr, while the same raw output is archived without filtering.

### Design

Replace the current fire-and-forget subprocess output mode with wrapper-managed tee capture:

- start RD-Agent with `stdout=PIPE`, `stderr=PIPE`
- read stdout and stderr concurrently
- append raw lines to:
  - `stdout.raw.log`
  - `stderr.raw.log`
  - `console.raw.log`
- immediately forward the same raw text to the wrapper process stdout/stderr
- flush on each write to keep logs durable and live output timely

This preserves operator visibility and creates durable raw artifacts.

### Why stderr must be first-class

Successful runs can still emit stderr noise or warnings. To verify "normal work without hidden errors", the wrapper must persist stderr separately.

`run_metadata.json` should therefore include:

- `stdout_line_count`
- `stderr_line_count`
- `stderr_nonempty`
- `log_capture_complete`

## Structured Event Stream

Add `events.jsonl`, one JSON object per line.

Each event should contain:

- `ts`
- `level`
- `event`
- `run_id`
- `workspace_dir`
- `step`
- `message`
- `data`

Representative events:

- `run_started`
- `sync_started`
- `sync_completed`
- `prepare_data_started`
- `prepare_data_completed`
- `prepare_data_failed`
- `rdagent_started`
- `rdagent_stdout_line`
- `rdagent_stderr_line`
- `rdagent_completed`
- `rdagent_failed`
- `factor_collection_started`
- `factor_collection_completed`
- `artifact_written`
- `dropbox_upload_started`
- `dropbox_upload_completed`
- `dropbox_upload_failed`
- `run_completed`
- `run_failed`

Raw logs remain the source of truth for full text. `events.jsonl` is the searchable index.

## Artifact Index

Add `run_artifacts.json` listing files produced during the run and whether each was uploaded to Dropbox archive.

Suggested shape:

```json
{
  "run_id": "2026-03-17T23-15-30Z",
  "workspace_dir": "C:/.../workspace/20260317_231530",
  "artifacts": [
    {
      "name": "stderr.raw.log",
      "path": "C:/.../stderr.raw.log",
      "kind": "log",
      "exists": true,
      "uploaded": true
    }
  ]
}
```

This allows simple audit and future automation.

## Failure Semantics

Failure paths must still emit diagnosable artifacts.

If RD-Agent fails after workspace creation, the wrapper should still attempt to write and archive:

- `events.jsonl`
- `stdout.raw.log`
- `stderr.raw.log`
- `console.raw.log`
- `run_metadata.json`
- `run_artifacts.json`

Status values should distinguish:

- `success`
- `no_factors`
- `failed`
- `failed_after_partial_artifacts`

The design bias is "archive first, then fail".

## Dropbox Contract Additions

New remote root:

- `/qlib_shared/rdagent_outputs/runs/<run_id>/...`

Existing factor outputs remain unchanged.

This design intentionally avoids modifying scanner ingestion paths. Scanner continues consuming the factor contract only.

## Testing Strategy

Use TDD to cover:

- run archive path creation and file naming
- tee capture of stdout/stderr into raw files
- preservation of live output forwarding
- event stream emission for success and failure paths
- Dropbox upload of archive batches
- compatibility with existing `run_log.json` and factor upload behavior
- failed subprocess runs still producing archiveable logs

## Implementation Notes

- Keep changes scoped to wrapper code in `src/main.py`, `src/runner/qlib_runner.py`, and `src/bridge/dropbox_sync.py`
- Prefer small helper functions for archive paths, event emission, and upload manifests
- Avoid building a large logging framework; local utilities are sufficient
