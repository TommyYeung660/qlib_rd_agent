"""CLI entry point for qlib_rd_agent.

Commands:
    sync   — Download scanner's shared data from Dropbox
    run    — Launch RD-Agent Qlib scenario
    upload — Upload discovered factors to Dropbox
    full   — Run all three steps in sequence (sync → run → upload)
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

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


def _write_json_file(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


def _prepare_run_context(config):
    from src.runner.qlib_runner import (
        _append_run_event,
        _build_run_id,
        _build_workspace_dir,
        _initialize_run_archive,
    )

    start_time = datetime.utcnow()
    run_id = _build_run_id(start_time)
    workspace_dir = _build_workspace_dir(config.rdagent.workspace_dir, start_time)
    archive_paths = _initialize_run_archive(workspace_dir, run_id)
    stream_counts = {"stdout": 0, "stderr": 0}
    _append_run_event(
        archive_paths,
        level="INFO",
        event="run_started",
        run_id=run_id,
        workspace_dir=str(workspace_dir),
        step="run",
        message="Run context initialized",
        data={"workspace_dir": str(workspace_dir)},
    )
    return start_time, run_id, workspace_dir, archive_paths, stream_counts


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
    from src.runner.qlib_runner import (
        _append_run_event,
        _format_run_metadata,
        _write_run_artifacts_index,
        collect_factors,
        run_rdagent,
    )

    config = ctx.obj["config"]

    if max_iterations is not None:
        config.rdagent.max_iterations = max_iterations
        logger.info("Overriding max_iterations to {}", max_iterations)

    start_time, run_id, workspace_dir, archive_paths, stream_counts = _prepare_run_context(config)
    factors_path = None
    run_error = None
    return_code = 0

    logger.info(
        "Launching RD-Agent (max_iterations={})...", config.rdagent.max_iterations
    )
    try:
        workspace_dir = run_rdagent(
            config,
            workspace_dir=workspace_dir,
            run_id=run_id,
            archive_paths=archive_paths,
            stream_counts=stream_counts,
        )

        logger.info("Collecting discovered factors from workspace...")
        _append_run_event(
            archive_paths,
            level="INFO",
            event="factor_collection_started",
            run_id=run_id,
            workspace_dir=str(workspace_dir),
            step="factor_collection",
            message="Collecting factors from workspace",
        )
        factors_path = collect_factors(str(workspace_dir), config=config)
        _append_run_event(
            archive_paths,
            level="INFO",
            event="factor_collection_completed",
            run_id=run_id,
            workspace_dir=str(workspace_dir),
            step="factor_collection",
            message="Factor collection completed",
            data={"factors_path": factors_path},
        )
        if factors_path:
            logger.info("Factors collected: {}", factors_path)
        else:
            logger.warning("No factors discovered in this run")
    except Exception as exc:
        run_error = exc
        return_code = 1
        logger.exception("RD-Agent run failed: {}", exc)
        _append_run_event(
            archive_paths,
            level="ERROR",
            event="run_failed",
            run_id=run_id,
            workspace_dir=str(workspace_dir),
            step="run",
            message="RD-Agent run command failed",
            data={"error": str(exc)},
        )
        factors_path = collect_factors(str(workspace_dir), config=config)
    finally:
        end_time = datetime.utcnow()
        if run_error is None:
            _append_run_event(
                archive_paths,
                level="INFO",
                event="run_completed",
                run_id=run_id,
                workspace_dir=str(workspace_dir),
                step="run",
                message="RD-Agent run command completed",
                data={"factors_path": factors_path},
            )
        _write_run_artifacts_index(
            workspace_dir=workspace_dir,
            run_id=run_id,
            archive_paths=archive_paths,
        )
        run_metadata = _format_run_metadata(
            config=config,
            start_time=start_time,
            end_time=end_time,
            return_code=return_code,
            workspace_dir=str(workspace_dir),
            factors_path=factors_path,
            run_id=run_id,
            archive_paths=archive_paths,
            stream_counts=stream_counts,
            log_capture_complete=True,
        )
        _write_json_file(archive_paths["metadata"], run_metadata)

    if run_error is not None:
        raise run_error


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
    from src.bridge.dropbox_sync import upload_factors, upload_run_archive, upload_run_log

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
    archive_dir = Path(factors_path).resolve().parent
    run_metadata_path = archive_dir / "run_metadata.json"
    if run_metadata_path.exists():
        run_metadata = json.loads(run_metadata_path.read_text(encoding="utf-8"))
        run_id = run_metadata.get("run_id")
        if run_id:
            upload_run_archive(config, archive_dir, run_id)
            upload_run_log(config, run_metadata)
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
    import shutil

    from src.bridge.dropbox_sync import (
        download_shared_data,
        upload_factors,
        upload_run_archive,
        upload_run_log,
    )
    from src.runner.qlib_runner import (
        _append_run_event,
        _format_run_metadata,
        _write_run_artifacts_index,
        collect_factors,
        run_rdagent,
    )

    config = ctx.obj["config"]
    start_time, run_id, workspace_dir, archive_paths, stream_counts = _prepare_run_context(config)
    factors_path = None
    run_error = None
    return_code = 0

    # ------------------------------------------------------------------
    # Step 1: Sync
    # ------------------------------------------------------------------
    try:
        if not skip_sync:
            logger.info("[1/3] Downloading shared data from Dropbox...")
            _append_run_event(
                archive_paths,
                level="INFO",
                event="sync_started",
                run_id=run_id,
                workspace_dir=str(workspace_dir),
                step="sync",
                message="Downloading shared data from Dropbox",
            )
            download_shared_data(config)
            _append_run_event(
                archive_paths,
                level="INFO",
                event="sync_completed",
                run_id=run_id,
                workspace_dir=str(workspace_dir),
                step="sync",
                message="Shared data download completed",
            )
        else:
            logger.info("[1/3] Skipping sync (--skip-sync)")
            _append_run_event(
                archive_paths,
                level="INFO",
                event="sync_skipped",
                run_id=run_id,
                workspace_dir=str(workspace_dir),
                step="sync",
                message="Skipped shared data download",
            )

        # ------------------------------------------------------------------
        # Step 2: Run RD-Agent
        # ------------------------------------------------------------------
        if max_iterations is not None:
            config.rdagent.max_iterations = max_iterations

        logger.info(
            "[2/3] Launching RD-Agent (max_iterations={})...", config.rdagent.max_iterations
        )
        workspace_dir = run_rdagent(
            config,
            workspace_dir=workspace_dir,
            run_id=run_id,
            archive_paths=archive_paths,
            stream_counts=stream_counts,
        )

        logger.info("Collecting discovered factors...")
        _append_run_event(
            archive_paths,
            level="INFO",
            event="factor_collection_started",
            run_id=run_id,
            workspace_dir=str(workspace_dir),
            step="factor_collection",
            message="Collecting discovered factors from workspace",
        )
        factors_path = collect_factors(str(workspace_dir), config=config)
        _append_run_event(
            archive_paths,
            level="INFO",
            event="factor_collection_completed",
            run_id=run_id,
            workspace_dir=str(workspace_dir),
            step="factor_collection",
            message="Factor collection completed",
            data={"factors_path": factors_path},
        )
    except Exception as exc:
        run_error = exc
        return_code = 1
        logger.exception("Full pipeline failed: {}", exc)
        _append_run_event(
            archive_paths,
            level="ERROR",
            event="run_failed",
            run_id=run_id,
            workspace_dir=str(workspace_dir),
            step="run",
            message="Full pipeline failed",
            data={"error": str(exc)},
        )
        factors_path = collect_factors(str(workspace_dir), config=config)

    # ------------------------------------------------------------------
    # Step 3: Upload results
    # ------------------------------------------------------------------
    if factors_path:
        logger.info("[3/3] Uploading discovered factors to Dropbox...")
        _append_run_event(
            archive_paths,
            level="INFO",
            event="factor_upload_started",
            run_id=run_id,
            workspace_dir=str(workspace_dir),
            step="upload",
            message="Uploading factor artifacts to Dropbox",
        )
        upload_factors(config, factors_path)

        local_factors_dir = Path(config.dropbox.local_factors_dir)
        local_factors_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(factors_path, local_factors_dir / "discovered_factors.yaml")
        logger.info("Factors copied to {}", local_factors_dir)
    else:
        logger.warning("[3/3] No factors to upload")

    end_time = datetime.utcnow()
    if run_error is None:
        _append_run_event(
            archive_paths,
            level="INFO",
            event="run_completed",
            run_id=run_id,
            workspace_dir=str(workspace_dir),
            step="run",
            message="Full pipeline completed before Dropbox archival",
            data={"factors_path": factors_path},
        )
    run_metadata = _format_run_metadata(
        config=config,
        start_time=start_time,
        end_time=end_time,
        return_code=return_code,
        workspace_dir=str(workspace_dir),
        factors_path=factors_path,
        run_id=run_id,
        archive_paths=archive_paths,
        stream_counts=stream_counts,
        log_capture_complete=True,
    )
    _write_run_artifacts_index(
        workspace_dir=workspace_dir,
        run_id=run_id,
        archive_paths=archive_paths,
    )
    _write_json_file(archive_paths["metadata"], run_metadata)
    _append_run_event(
        archive_paths,
        level="INFO",
        event="dropbox_upload_started",
        run_id=run_id,
        workspace_dir=str(workspace_dir),
        step="upload",
        message="Uploading immutable run archive to Dropbox",
        data={"has_factors": bool(factors_path)},
    )
    upload_run_archive(config, workspace_dir, run_id)
    upload_run_log(config, run_metadata)

    duration = (end_time - start_time).total_seconds()
    logger.info(
        "Pipeline complete in {:.0f}s — status: {}, factors: {}",
        duration,
        run_metadata["status"],
        factors_path or "none",
    )

    if run_error is not None:
        raise run_error


def main() -> None:
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
