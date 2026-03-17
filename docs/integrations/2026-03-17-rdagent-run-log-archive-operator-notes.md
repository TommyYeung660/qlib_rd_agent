# RD-Agent Run Log Archive Operator Notes

This note describes the `v1.5.0` run log archive behavior in `qlib_rd_agent`.

## What changes

Every `python -m src.main full` run now produces:

- raw child process stdout in `stdout.raw.log`
- raw child process stderr in `stderr.raw.log`
- merged raw console output in `console.raw.log`
- structured event timeline in `events.jsonl`
- run summary in `run_metadata.json`
- artifact index in `run_artifacts.json`

## Dropbox layout

Each run is archived under an immutable path:

```text
/qlib_shared/rdagent_outputs/runs/<run_id>/
```

Expected files:

- `run_metadata.json`
- `run_artifacts.json`
- `events.jsonl`
- `console.raw.log`
- `stdout.raw.log`
- `stderr.raw.log`
- optionally the factor artifacts when they were produced:
  - `discovered_factors.yaml`
  - `candidate_factors.yaml`
  - `factor_manifest.json`

## Latest pointers remain

These paths still update for compatibility:

- `/qlib_shared/rdagent_outputs/run_log.json`
- `/qlib_shared/rdagent_outputs/factors/discovered_factors.yaml`
- `/qlib_shared/rdagent_outputs/factors/candidate_factors.yaml`
- `/qlib_shared/rdagent_outputs/factors/factor_manifest.json`

Treat them as latest pointers only. Historical analysis should use `runs/<run_id>/`.

## Recommended inspection order

If you need to diagnose a run:

1. Open `run_metadata.json`
2. Check `stderr_line_count` and `stderr_nonempty`
3. Read `stderr.raw.log`
4. Read `events.jsonl`
5. Compare `run_artifacts.json` with the expected archive files

## Practical interpretation

- `stderr_nonempty = false` means the wrapper did not observe any stderr lines from the RD-Agent subprocess
- `status = no_factors` means the run finished without a discovered factor batch
- `status = failed` means the subprocess or wrapper encountered an error, but archive artifacts should still exist locally and, when upload succeeds, in Dropbox
