# RD-Agent Candidate Contract Design

> **Date:** 2026-03-17
>
> **Version Target:** `v1.5.0` scanner compatibility
>
> **Owner Repo:** `qlib_rd_agent`
>
> **Downstream Consumer:** `qlib_market_scanner`

---

## 1. Purpose

This document defines how `qlib_rd_agent` should publish discovered factor artifacts so that `qlib_market_scanner` can safely consume them through its new `candidate -> promoted -> FX-only load` chain.

The objective is compatibility first:

- preserve the current `discovered_factors.yaml` flow
- add a first-class `candidate_factors.yaml` artifact
- add machine-readable manifest metadata for audit and downstream gating

---

## 2. Current State

Today `qlib_rd_agent`:

- extracts factors into `discovered_factors.yaml`
- uploads only that file to Dropbox
- writes run metadata separately as `run_log.json`

This works for a legacy scanner integration, but it does not explicitly label the factor artifact as a `candidate` stage artifact.

---

## 3. Target Contract

Each RD-Agent run that discovers factors must emit three artifacts inside the workspace:

1. `discovered_factors.yaml`
- legacy compatibility artifact
- unchanged top-level schema: `factors: [...]`

2. `candidate_factors.yaml`
- canonical downstream artifact for scanner ingestion
- same `factors: [...]` schema as `discovered_factors.yaml`
- semantically represents raw candidate factors awaiting scanner-local promotion

3. `factor_manifest.json`
- machine-readable metadata sidecar
- must include:
  - `stage: "candidate"`
  - `generator: "qlib_rd_agent"`
  - `generated_at`
  - `workspace_dir`
  - `factor_count`
  - `legacy_artifact`
  - `candidate_artifact`
  - `chat_model`
  - `embedding_model`
  - `max_iterations`

---

## 4. Dropbox Publishing

Dropbox upload must remain backward compatible and publish:

- `.../factors/discovered_factors.yaml`
- `.../factors/candidate_factors.yaml`
- `.../factors/factor_manifest.json`

This allows:

- old consumers to keep reading `discovered_factors.yaml`
- new scanner logic to prefer `candidate_factors.yaml`
- operators to inspect run provenance via the manifest

---

## 5. Compatibility Rules

- `discovered_factors.yaml` must remain present if factors were found.
- `candidate_factors.yaml` must be content-compatible with the scanner's current factor loader.
- no scanner-specific promotion logic should move into `qlib_rd_agent`
- the RD-Agent repo remains responsible only for generating `candidate` artifacts, not `promoted` artifacts

---

## 6. Acceptance Criteria

The change is complete when:

1. `collect_factors()` emits both YAML artifacts plus the JSON manifest.
2. `upload_factors()` uploads all three files.
3. `full` and `upload` flows still work when only `discovered_factors.yaml` is referenced.
4. README documents the new candidate artifact flow.
5. Focused tests cover artifact emission and upload mapping.
