# qlib_rd_agent

Qlib RD-Agent orchestration layer — automated factor mining with Microsoft RD-Agent, communicating with `qlib_market_scanner` via Dropbox.

## Architecture

- **Chat model**: Volcengine glm-4.7 (via LiteLLM proxy)
- **Embedding model**: AIHUBMIX text-embedding-3-small
- **Runtime**: WSL2 Ubuntu 22.04 on GPU Windows PC
- **Data sync**: Dropbox shared folder (`/qlib_shared/`)

## Quick Start

```bash
# 1. Clone
git clone https://github.com/TommyYeung660/qlib_rd_agent.git
cd qlib_rd_agent

# 2. Setup (GPU Windows PC)
# Phase 1 — Windows side (admin PowerShell)
.\scripts\setup_windows.ps1

# Phase 2 — WSL side
cd ~/qlib_rd_agent && ./scripts/setup_wsl.sh

# 3. Configure
cp .env.example .env
# Edit .env with your API keys

# 4. Run
python -m src.main full
```

## Commands

| Command | Description |
|---------|-------------|
| `python -m src.main sync` | Download data from Dropbox |
| `python -m src.main run` | Run RD-Agent factor mining |
| `python -m src.main upload` | Upload discovered factors to Dropbox |
| `python -m src.main full` | sync → run → upload (all-in-one) |

## Factor artifacts

Each successful factor collection now emits three artifacts in the RD-Agent workspace:

- `discovered_factors.yaml`
  - legacy compatibility artifact
  - kept for existing scripts and older consumers
- `candidate_factors.yaml`
  - canonical scanner-facing candidate artifact
  - intended for `qlib_market_scanner` candidate ingestion
- `factor_manifest.json`
  - metadata sidecar with run provenance, factor count, and model settings

Dropbox upload publishes all three artifacts under:

- `/qlib_shared/rdagent_outputs/factors/discovered_factors.yaml`
- `/qlib_shared/rdagent_outputs/factors/candidate_factors.yaml`
- `/qlib_shared/rdagent_outputs/factors/factor_manifest.json`

This keeps the old `discovered_factors.yaml` path stable while giving the scanner an explicit `candidate`-stage contract to promote locally.

## Run log archives

For `v1.5.0`, each `full` run now produces an immutable log batch in the local workspace and uploads the same batch to Dropbox.

Local workspace artifacts now include:

- `run_metadata.json`
- `run_artifacts.json`
- `events.jsonl`
- `console.raw.log`
- `stdout.raw.log`
- `stderr.raw.log`

Dropbox keeps a per-run archive under:

- `/qlib_shared/rdagent_outputs/runs/<run_id>/run_metadata.json`
- `/qlib_shared/rdagent_outputs/runs/<run_id>/run_artifacts.json`
- `/qlib_shared/rdagent_outputs/runs/<run_id>/events.jsonl`
- `/qlib_shared/rdagent_outputs/runs/<run_id>/console.raw.log`
- `/qlib_shared/rdagent_outputs/runs/<run_id>/stdout.raw.log`
- `/qlib_shared/rdagent_outputs/runs/<run_id>/stderr.raw.log`

Compatibility pointers remain in place:

- `/qlib_shared/rdagent_outputs/run_log.json` stays as the latest-only summary
- `/qlib_shared/rdagent_outputs/factors/...` stays as the latest factor hand-off path

`stderr.raw.log` is preserved separately so operators can verify whether a run stayed quiet on stderr even when the overall status is `success`.

## End-to-end hand-off

For `v1.5.0`, this repo is only the upstream candidate generator in the FX factor loop.

Recommended operating sequence:

1. `qlib_market_scanner` publishes the latest FX `1d` shared bundle with `python -m src.main --profile fx --interval 1d --share-data`
2. `qlib_rd_agent` runs `python -m src.main full` on the GPU / WSL2 machine and uploads factor artifacts to Dropbox
3. `qlib_market_scanner` pulls the new batch with `python -m src.main --profile fx --interval 1d --sync-rdagent-factors --enable-rdagent-factors`

Important boundaries:

- this repo does not decide promotion
- this repo does not write directly into the scanner feature set
- the scanner remains the final safety gate
- the official `v1.5.0` FX cadence remains `1d`
