"""CLI entry point for qlib_rd_agent.

Commands:
    sync   — Download scanner's shared data from Dropbox
    run    — Launch RD-Agent Qlib scenario
    upload — Upload discovered factors to Dropbox
    full   — Run all three steps in sequence (sync → run → upload)
"""

from __future__ import annotations

import sys
from datetime import datetime

import click
from loguru import logger

from src.config import load_config


def _setup_logging(log_level: str) -> None:
    """Configure loguru logger with the given level.

    Args:
        log_level: Logging level string (DEBUG, INFO, WARNING, ERROR).
    """
    logger.remove()
    logger.add(
        sys.stderr,
        level=log_level.upper(),
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level:<8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> — <level>{message}</level>",
    )


@click.group()
@click.option(
    "--log-level",
    default=None,
    help="Override log level (DEBUG, INFO, WARNING, ERROR).",
)
@click.pass_context
def cli(ctx: click.Context, log_level: str | None) -> None:
    """qlib_rd_agent — Automated factor mining with Microsoft RD-Agent."""
    ctx.ensure_object(dict)
    config = load_config()

    effective_level = log_level or config.log_level
    _setup_logging(effective_level)

    ctx.obj["config"] = config


@cli.command()
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Force download even if local data is up-to-date.",
)
@click.pass_context
def sync(ctx: click.Context, force: bool) -> None:
    """Download scanner's shared data from Dropbox."""
    from src.bridge.dropbox_sync import (
        check_remote_data_freshness,
        download_shared_data,
    )

    config = ctx.obj["config"]

    if not force:
        logger.info("Checking remote data freshness...")
        remote_manifest = check_remote_data_freshness(config)
        if remote_manifest is None:
            logger.info("Local data is up-to-date. Use --force to re-download.")
            return

    logger.info("Downloading shared data from Dropbox...")
    local_dir = download_shared_data(config)
    logger.info("Sync complete: {}", local_dir)


@cli.command()
@click.option(
    "--max-iterations", default=None, type=int, help="Override max RD-Agent iterations."
)
@click.pass_context
def run(ctx: click.Context, max_iterations: int | None) -> None:
    """Launch RD-Agent Qlib scenario."""
    from src.runner.qlib_runner import collect_factors, run_rdagent

    config = ctx.obj["config"]

    if max_iterations is not None:
        config.rdagent.max_iterations = max_iterations
        logger.info("Overriding max_iterations to {}", max_iterations)

    logger.info(
        "Launching RD-Agent (max_iterations={})...", config.rdagent.max_iterations
    )
    workspace_dir = run_rdagent(config)

    logger.info("Collecting discovered factors from workspace...")
    factors_path = collect_factors(str(workspace_dir))
    if factors_path:
        logger.info("Factors collected: {}", factors_path)
    else:
        logger.warning("No factors discovered in this run")


@cli.command()
@click.option(
    "--factors-path",
    default=None,
    type=str,
    help="Path to discovered_factors.yaml. Auto-detected if not set.",
)
@click.pass_context
def upload(ctx: click.Context, factors_path: str | None) -> None:
    """Upload discovered factors to Dropbox."""
    from pathlib import Path

    from src.bridge.dropbox_sync import upload_factors

    config = ctx.obj["config"]

    if factors_path is None:
        # Auto-detect: check workspace first, then local factors dir
        candidates = [
            Path(config.rdagent.workspace_dir) / "discovered_factors.yaml",
            Path(config.dropbox.local_factors_dir) / "discovered_factors.yaml",
        ]
        for candidate in candidates:
            if candidate.exists():
                factors_path = str(candidate)
                logger.info("Auto-detected factors file: {}", factors_path)
                break

    if factors_path is None:
        logger.error(
            "No discovered_factors.yaml found. Specify --factors-path or run RD-Agent first."
        )
        sys.exit(1)

    upload_factors(config, factors_path)
    logger.info("Upload complete")


@cli.command()
@click.option(
    "--max-iterations", default=None, type=int, help="Override max RD-Agent iterations."
)
@click.option(
    "--skip-sync",
    is_flag=True,
    default=False,
    help="Skip the sync step (use existing local data).",
)
@click.pass_context
def full(ctx: click.Context, max_iterations: int | None, skip_sync: bool) -> None:
    """Run complete pipeline: sync → run → upload."""
    from pathlib import Path

    from src.bridge.dropbox_sync import upload_factors, upload_run_log
    from src.runner.qlib_runner import collect_factors, run_rdagent

    config = ctx.obj["config"]
    start_time = datetime.now()

    # ------------------------------------------------------------------
    # Step 1: Sync
    # ------------------------------------------------------------------
    if not skip_sync:
        from src.bridge.dropbox_sync import download_shared_data

        logger.info("[1/3] Downloading shared data from Dropbox...")
        download_shared_data(config)
    else:
        logger.info("[1/3] Skipping sync (--skip-sync)")

    # ------------------------------------------------------------------
    # Step 2: Run RD-Agent
    # ------------------------------------------------------------------
    if max_iterations is not None:
        config.rdagent.max_iterations = max_iterations

    logger.info(
        "[2/3] Launching RD-Agent (max_iterations={})...", config.rdagent.max_iterations
    )
    workspace_dir = run_rdagent(config)

    logger.info("Collecting discovered factors...")
    factors_path = collect_factors(str(workspace_dir))

    # ------------------------------------------------------------------
    # Step 3: Upload results
    # ------------------------------------------------------------------
    end_time = datetime.now()
    status = "success" if factors_path else "no_factors"

    if factors_path:
        logger.info("[3/3] Uploading discovered factors to Dropbox...")
        upload_factors(config, factors_path)

        # Also copy to local factors dir for reference
        local_factors_dir = Path(config.dropbox.local_factors_dir)
        local_factors_dir.mkdir(parents=True, exist_ok=True)
        import shutil

        shutil.copy2(factors_path, local_factors_dir / "discovered_factors.yaml")
        logger.info("Factors copied to {}", local_factors_dir)
    else:
        logger.warning("[3/3] No factors to upload")

    # Upload run metadata
    run_metadata = {
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "duration_seconds": (end_time - start_time).total_seconds(),
        "status": status,
        "max_iterations": config.rdagent.max_iterations,
        "chat_model": config.llm.chat_model,
        "embedding_model": config.llm.embedding_model,
        "factors_discovered": factors_path is not None,
        "workspace_dir": str(workspace_dir),
    }
    upload_run_log(config, run_metadata)

    duration = (end_time - start_time).total_seconds()
    logger.info(
        "Pipeline complete in {:.0f}s — status: {}, factors: {}",
        duration,
        status,
        factors_path or "none",
    )


def main() -> None:
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
