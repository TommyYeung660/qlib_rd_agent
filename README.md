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
