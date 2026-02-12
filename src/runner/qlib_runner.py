from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from loguru import logger

from src.config import AppConfig
from src.runner.patch_generated_code import patch_generated_code_in_workspace


def _find_conda_executable() -> str:
    """Locate the conda executable, checking common Miniforge/Miniconda paths.

    Returns:
        Absolute path to the conda binary.

    Raises:
        FileNotFoundError: If conda cannot be found anywhere.
    """
    import shutil

    # 1. Already on PATH?
    conda_path = shutil.which("conda")
    if conda_path:
        return conda_path

    # 2. Check common installation directories
    home = Path.home()
    candidates = [
        home / "miniforge3" / "bin" / "conda",
        home / "miniforge3" / "condabin" / "conda",
        home / "miniconda3" / "bin" / "conda",
        home / "miniconda3" / "condabin" / "conda",
        home / "anaconda3" / "bin" / "conda",
        Path("/opt/conda/bin/conda"),
    ]
    for candidate in candidates:
        if candidate.exists():
            logger.debug("Found conda at: {}", candidate)
            return str(candidate)

    raise FileNotFoundError(
        "conda executable not found on PATH or in standard locations: "
        + ", ".join(str(c) for c in candidates)
    )


def _resolve_path(path_str: str) -> Path:
    """Resolve a path string, expanding ``~`` to the user's home directory.

    Args:
        path_str: Path string that may contain ``~``.

    Returns:
        Fully resolved :class:`~pathlib.Path`.
    """
    return Path(path_str).expanduser().resolve()


def _build_rdagent_env(config: AppConfig) -> Dict[str, str]:
    """Build environment variables dict for RD-Agent subprocess.

    Inherits the current ``os.environ`` as a base and overlays RD-Agent
    specific settings derived from *config*.

    Environment variables set:
        - ``PYTHONUNBUFFERED``        – ``"1"`` (force unbuffered output)
        - ``BACKEND``                 – ``"rdagent.oai.backend.LiteLLMAPIBackend"``
        - ``CHAT_MODEL``              – e.g. ``"volcengine/glm-4.7"``
        - ``EMBEDDING_MODEL``         – e.g. ``"litellm_proxy/text-embedding-3-small"``
        - ``VOLCENGINE_API_KEY``      – API key for Volcengine (火山引擎)
        - ``VOLCENGINE_API_BASE``     – e.g. ``"https://ark.cn-beijing.volces.com/api/v3"``
        - ``LITELLM_PROXY_API_KEY``   – API key for the embedding provider (AIHUBMIX)
        - ``LITELLM_PROXY_API_BASE``  – e.g. ``"https://aihubmix.com/v1"``
        - ``OPENAI_API_KEY``          – fallback key (set to volcengine key)
        - ``MAX_CONCURRENT_REQUESTS`` – concurrency cap for LLM calls
        - ``REQUEST_TIMEOUT``         – per-request timeout in seconds
        - ``QLIB_DATA_PATH``          – path to Qlib binary data
        - ``MAX_ITERATIONS``          – max RD-Agent evolution iterations

    Args:
        config: Application configuration containing LLM and RD-Agent settings.

    Returns:
        A new *dict* suitable for passing as ``env`` to :func:`subprocess.Popen`.
    """
    env = os.environ.copy()

    # ── Force unbuffered Python output ──
    # When Python runs in a non-TTY subprocess (PIPE), it enables full buffering by default.
    # This causes output to be stuck in the buffer until the process exits or buffer fills.
    # Setting PYTHONUNBUFFERED=1 forces line-buffered output even in non-TTY mode.
    env["PYTHONUNBUFFERED"] = "1"

    # ── LiteLLM backend selection ──
    # RD-Agent reads BACKEND to pick the API backend class.
    # See: rdagent/oai/llm_conf.py -> LLMSettings.backend
    env["BACKEND"] = "rdagent.oai.backend.LiteLLMAPIBackend"

    # ── Force OpenAI Provider Logic for Volcengine ──
    # We use the "coding" endpoint which supports generic model names.
    # To avoid LiteLLM's strict endpoint checks for 'volcengine' provider,
    # we masquerade as 'openai' provider but point to Volcengine's URL.
    # This requires specific env vars to be set.

    # 1. Force clear proxies to match debug_litellm.py success state
    for proxy_var in [
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "http_proxy",
        "https_proxy",
        "ALL_PROXY",
        "all_proxy",
    ]:
        if proxy_var in os.environ:
            del os.environ[proxy_var]
            if proxy_var in env:
                del env[proxy_var]

    # 2. Inject Volcengine credentials as OpenAI vars for the child process
    env["OPENAI_API_KEY"] = config.llm.volcengine_api_key
    env["OPENAI_BASE_URL"] = (
        config.llm.volcengine_base_url
    )  # LiteLLM uses OPENAI_BASE_URL
    env["OPENAI_API_BASE"] = config.llm.volcengine_base_url  # Legacy support

    # 3. Ensure Volcengine vars are also present (LiteLLM might look for them)
    env["VOLCENGINE_API_KEY"] = config.llm.volcengine_api_key
    env["VOLCENGINE_API_BASE"] = config.llm.volcengine_base_url

    # 4. Force CHAT_MODEL to use openai/ prefix directly
    # This bypasses litellm_config.yaml mapping issues and forces the provider
    env["CHAT_MODEL"] = "openai/glm-4.7"

    # ── Embedding model settings ──
    # When chat and embedding use DIFFERENT providers, RD-Agent docs say:
    #   EMBEDDING_MODEL=litellm_proxy/<model_name>
    #   LITELLM_PROXY_API_KEY=<embedding_provider_key>
    #   LITELLM_PROXY_API_BASE=<embedding_provider_base>
    # See: https://github.com/microsoft/RD-Agent/blob/main/docs/installation_and_configuration.rst

    # Fix: Ensure model name uses litellm_proxy/ prefix if we are using the proxy vars
    embedding_model = config.llm.embedding_model
    if embedding_model.startswith("aihubmix/"):
        embedding_model = embedding_model.replace("aihubmix/", "litellm_proxy/")
    elif (
        not embedding_model.startswith("litellm_proxy/") and config.llm.aihubmix_api_key
    ):
        # If user didn't specify prefix but provided aihubmix key, assume proxy
        # But be careful not to break other providers.
        # For now, just handle the aihubmix/ case which is in the default config.
        pass

    env["EMBEDDING_MODEL"] = embedding_model
    env["LITELLM_PROXY_API_KEY"] = config.llm.aihubmix_api_key
    env["LITELLM_PROXY_API_BASE"] = config.llm.aihubmix_base_url

    # ── Fallback OPENAI_API_KEY ──
    # Some RD-Agent code paths (health_check, token counting) still reference
    # OPENAI_API_KEY as a fallback.  Set it to the volcengine key so those
    # paths don't crash.
    env["OPENAI_API_KEY"] = config.llm.volcengine_api_key

    # ── Concurrency & timeout ──
    env["MAX_CONCURRENT_REQUESTS"] = str(config.llm.max_concurrent_requests)
    env["REQUEST_TIMEOUT"] = str(config.llm.request_timeout)

    # ── RD-Agent scenario hints ──
    env["QLIB_DATA_PATH"] = str(_resolve_path(config.rdagent.qlib_data_path))
    env["MAX_ITERATIONS"] = str(config.rdagent.max_iterations)

    # ── Force Local Execution (No Docker) ──
    # This tells RD-Agent's ModelCoSTEER to use QlibCondaEnv instead of QTDockerEnv.
    env["MODEL_COSTEER_ENV_TYPE"] = "conda"

    # ── Force Clear Proxy Settings ──
    # LiteLLM / RD-Agent can fail if proxies are set (Country not supported error).
    # We clear them for the subprocess environment only.
    for proxy_key in [
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "http_proxy",
        "https_proxy",
        "ALL_PROXY",
    ]:
        if proxy_key in env:
            del env[proxy_key]

    logger.debug(
        "RD-Agent env overlay — BACKEND={}, CHAT_MODEL={}, EMBEDDING_MODEL={}",
        env["BACKEND"],
        env["CHAT_MODEL"],
        env["EMBEDDING_MODEL"],
    )
    return env


def _setup_qlib_data_symlinks(config: AppConfig) -> None:
    """Create symlinks from common hardcoded Qlib paths to actual QLIB_DATA_PATH.

    RD-Agent's LLM generates code with hardcoded paths like:
        - ~/.qlib/qlib_data/cn_data
        - /path/to/qlib_data/cn_data

    This function creates symlinks from these expected locations to the actual
    configured QLIB_DATA_PATH so that hardcoded paths still work.

    Args:
        config: Application configuration containing qlib_data_path.
    """
    actual_path = _resolve_path(config.rdagent.qlib_data_path)

    # List of common hardcoded paths the LLM might generate
    # (relative to home directory or absolute paths)
    symlink_targets = [
        Path.home() / ".qlib" / "qlib_data" / "cn_data",
        Path.home() / ".qlib" / "qlib_data",
        Path("/path/to/qlib_data/cn_data"),
        Path("/path/to/qlib_data"),
    ]

    for target_link in symlink_targets:
        try:
            # Skip if target doesn't exist (e.g., /path/to/...)
            if target_link.parent.exists() or target_link.parent == Path.home():
                # Ensure parent directory exists
                target_link.parent.mkdir(parents=True, exist_ok=True)

                # Create symlink if it doesn't exist
                if not target_link.exists():
                    target_link.symlink_to(actual_path)
                    logger.debug("Created symlink: {} -> {}", target_link, actual_path)
                elif target_link.is_symlink() and target_link.resolve() != actual_path:
                    # Update existing symlink if it points to wrong location
                    target_link.unlink()
                    target_link.symlink_to(actual_path)
                    logger.debug("Updated symlink: {} -> {}", target_link, actual_path)
        except (OSError, PermissionError) as exc:
            # Log but don't fail - some paths might not be creatable (e.g., /path/to/)
            logger.debug("Could not create symlink at {}: {}", target_link, exc)


def _verify_prerequisites(config: AppConfig) -> None:
    """Verify that required tools and data are available before launching RD-Agent.

    Checks performed (in order):
        1. ``config.rdagent.qlib_data_path`` exists and contains at least one file.
        2. ``conda`` CLI is reachable (``conda --version``).
        3. The conda environment named ``config.rdagent.conda_env_name`` exists.
        4. Volcengine and AIHUBMIX API keys are configured (non-empty).

    Args:
        config: Application configuration.

    Raises:
        RuntimeError: If any prerequisite check fails.
        FileNotFoundError: If Qlib binary data directory is missing or empty.
    """
    # 1. Qlib data path
    qlib_data = _resolve_path(config.rdagent.qlib_data_path)
    if not qlib_data.exists():
        raise FileNotFoundError(
            "Qlib data directory does not exist: {}".format(qlib_data)
        )
    data_files = list(qlib_data.iterdir())
    if not data_files:
        raise FileNotFoundError("Qlib data directory is empty: {}".format(qlib_data))
    logger.info("Qlib data OK — {} items in {}", len(data_files), qlib_data)

    # 2. Conda availability
    try:
        conda_bin = _find_conda_executable()
        result = subprocess.run(
            [conda_bin, "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "conda --version exited with code {}".format(result.returncode)
            )
        logger.info("Conda OK — {} ({})", result.stdout.strip(), conda_bin)
    except FileNotFoundError as exc:
        raise RuntimeError("conda is not installed or not on PATH") from exc

    # 3. Conda environment exists
    try:
        result = subprocess.run(
            [conda_bin, "env", "list", "--json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "conda env list failed with code {}".format(result.returncode)
            )
        env_data = json.loads(result.stdout)
        env_names = [Path(p).name for p in env_data.get("envs", [])]
        if config.rdagent.conda_env_name not in env_names:
            raise RuntimeError(
                "Conda env '{}' not found. Available: {}".format(
                    config.rdagent.conda_env_name, env_names
                )
            )
        logger.info("Conda env '{}' found", config.rdagent.conda_env_name)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Failed to parse conda env list output") from exc

    # 4. API keys configured
    if not config.llm.volcengine_api_key:
        raise RuntimeError(
            "VOLCENGINE_API_KEY is not set. "
            "Please add it to .env or set the environment variable."
        )
    logger.info("Volcengine API key configured")

    if not config.llm.aihubmix_api_key:
        raise RuntimeError(
            "AIHUBMIX_API_KEY is not set. "
            "Please add it to .env or set the environment variable."
        )
    logger.info("AIHUBMIX API key configured")


def run_rdagent(config: AppConfig) -> Path:
    """Launch RD-Agent Qlib scenario as a subprocess and stream its output.

    Execution steps:
        1. Verify all prerequisites (data, conda, API keys).
        2. Build environment variable overlay for the subprocess.
        3. Create (or reuse) a timestamped workspace directory.
        4. Launch ``python -m rdagent.app.qlib_rd_loop`` inside the configured
           conda environment via ``conda run``.
        5. Stream stdout / stderr line-by-line to :mod:`loguru`.
        6. On completion, invoke :func:`collect_factors` to gather results.
        7. Write run metadata via :func:`_format_run_metadata`.

    Args:
        config: Application configuration.

    Returns:
        :class:`~pathlib.Path` pointing to the workspace directory that
        contains RD-Agent outputs and (optionally) ``discovered_factors.yaml``.

    Raises:
        RuntimeError: If RD-Agent exits with a non-zero return code.
        FileNotFoundError: If Qlib data is not available.
    """
    start_time = datetime.now()

    # --- Step 1: prerequisites ---
    _verify_prerequisites(config)

    # --- Step 2: environment ---
    env = _build_rdagent_env(config)

    # --- Step 2.5: Setup symlinks for hardcoded paths ---
    # RD-Agent's LLM generates code with hardcoded paths like ~/.qlib/qlib_data/cn_data
    # Create symlinks from common hardcoded paths to the actual QLIB_DATA_PATH
    _setup_qlib_data_symlinks(config)

    # --- Step 3: workspace ---
    timestamp = start_time.strftime("%Y%m%d_%H%M%S")
    workspace_dir = _resolve_path(config.rdagent.workspace_dir) / timestamp
    workspace_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Workspace directory: {}", workspace_dir)

    # --- Step 3.5: Prepare Data (Bypass Docker) ---
    # Copy prep script to workspace
    prep_script_src = Path(__file__).parent / "prepare_data.py"
    if prep_script_src.exists():
        import shutil

        shutil.copy2(prep_script_src, workspace_dir / "prepare_data.py")

        # Run preparation in conda env
        conda_bin = _find_conda_executable()
        prep_cmd = [
            conda_bin,
            "run",
            "-n",
            config.rdagent.conda_env_name,
            "python",
            "prepare_data.py",
            env["QLIB_DATA_PATH"],
        ]
        logger.info("Running data preparation (to skip Docker requirement)...")
        try:
            subprocess.run(
                prep_cmd,
                check=True,
                env=env,
                cwd=str(workspace_dir),
                capture_output=False,  # Let it print to stdout
            )
        except subprocess.CalledProcessError as e:
            logger.error("Data preparation failed: {}", e)
            # We don't raise here, hoping RD-Agent might recover or user checks logs
    else:
        logger.warning(
            "prepare_data.py not found at {}, skipping local data gen", prep_script_src
        )

    # --- Step 4: launch command ---
    conda_bin = _find_conda_executable()
    cmd: List[str] = [
        conda_bin,
        "run",
        "-n",
        config.rdagent.conda_env_name,
        "rdagent",
        "fin_factor",
    ]
    logger.info("Launching RD-Agent: {}", " ".join(cmd))

    proc = subprocess.Popen(
        cmd,
        stdout=None,
        stderr=None,
        env=env,
        cwd=str(workspace_dir),
    )

    # --- Step 5: wait for completion ---
    # We stopped piping output (stdout=None) so that RD-Agent's progress bars (tqdm/rich)
    # work correctly in the terminal. The user needs to see real-time progress.
    return_code = proc.wait()
    end_time = datetime.now()

    # --- Step 6: collect results ---
    factors_path: Optional[str] = None
    if return_code == 0:
        logger.info("RD-Agent completed successfully (exit code 0)")
        factors_path = collect_factors(str(workspace_dir))
    else:
        logger.error(
            "RD-Agent exited with code {}. Attempting partial factor collection.",
            return_code,
        )
        factors_path = collect_factors(str(workspace_dir))

    # --- Step 7: metadata ---
    metadata = _format_run_metadata(
        config=config,
        start_time=start_time,
        end_time=end_time,
        return_code=return_code,
        workspace_dir=str(workspace_dir),
        factors_path=factors_path,
    )
    metadata_path = workspace_dir / "run_metadata.json"
    metadata_path.write_text(
        json.dumps(metadata, indent=2, default=str), encoding="utf-8"
    )
    logger.info("Run metadata written to {}", metadata_path)

    if return_code != 0:
        raise RuntimeError("RD-Agent exited with non-zero code: {}".format(return_code))

    return workspace_dir


def collect_factors(workspace_dir: str) -> Optional[str]:
    """Collect discovered factors from an RD-Agent workspace and write ``discovered_factors.yaml``.

    RD-Agent's Qlib scenario produces factor implementation code inside its
    workspace directory tree.  This function walks the tree looking for:

    * Python files containing Qlib-style expressions (``$close``, ``Ref(``, etc.).
    * JSON / YAML summary files that RD-Agent may generate.

    Discovered factors are normalised into the schema expected by
    ``qlib_market_scanner``:

    .. code-block:: yaml

        factors:
          - name: "FACTOR_NAME"
            expression: "$close / Ref($close, 5) - 1"
            ic_mean: null
            ic_ir: null
            description: "Auto-discovered by RD-Agent"
            enabled: true

    Args:
        workspace_dir: Absolute or relative path to the RD-Agent workspace.

    Returns:
        Absolute path (as *str*) to the generated ``discovered_factors.yaml``
        file, or ``None`` if no factors could be extracted.
    """
    ws = Path(workspace_dir)
    factors: List[Dict[str, Any]] = []

    # --- Strategy 1: scan for RD-Agent result JSON summaries ---
    for json_file in ws.rglob("*.json"):
        try:
            content = json_file.read_text(encoding="utf-8")
            data = json.loads(content)
            factors.extend(_extract_factors_from_json(data, source=str(json_file)))
        except (json.JSONDecodeError, OSError) as exc:
            logger.debug("Skipping {}: {}", json_file, exc)

    # --- Strategy 2: scan Python files for Qlib expressions ---
    qlib_expr_pattern = re.compile(
        r"""(\$\w+\s*[/\*\+\-]|Ref\s*\(|Mean\s*\(|Std\s*\(|Corr\s*\()"""
    )
    for py_file in ws.rglob("*.py"):
        try:
            source_code = py_file.read_text(encoding="utf-8")
            if qlib_expr_pattern.search(source_code):
                factor = _parse_factor_from_python(py_file, source_code)
                if factor is not None:
                    factors.append(factor)
        except OSError as exc:
            logger.debug("Skipping {}: {}", py_file, exc)

    # Deduplicate by name
    seen_names: set[str] = set()
    unique_factors: List[Dict[str, Any]] = []
    for f in factors:
        name = f.get("name", "")
        if name and name not in seen_names:
            seen_names.add(name)
            unique_factors.append(f)

    if not unique_factors:
        logger.warning("No factors discovered in workspace {}", workspace_dir)
        return None

    # Write YAML
    output_path = ws / "discovered_factors.yaml"
    output_data = {"factors": unique_factors}
    output_path.write_text(
        yaml.dump(output_data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    logger.info("Wrote {} discovered factors to {}", len(unique_factors), output_path)
    return str(output_path)


def _extract_factors_from_json(data: object, source: str) -> List[Dict[str, Any]]:
    """Extract factor definitions from a parsed JSON structure.

    RD-Agent may store results in varied formats.  This helper attempts
    several heuristics to locate factor-like entries.

    Args:
        data: Parsed JSON object (dict, list, or primitive).
        source: File path string used only for logging context.

    Returns:
        A list of factor dicts in the standard schema.  May be empty.
    """
    results: List[Dict[str, Any]] = []

    if isinstance(data, dict):
        # Check if the dict itself looks like a factor
        if "expression" in data or "factor_name" in data or "name" in data:
            factor = _normalise_factor_dict(data)
            if factor is not None:
                results.append(factor)

        # Recurse into values that are lists / dicts
        for value in data.values():
            results.extend(_extract_factors_from_json(value, source))

    elif isinstance(data, list):
        for item in data:
            results.extend(_extract_factors_from_json(item, source))

    return results


def _normalise_factor_dict(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalise a raw factor dict into the standard YAML schema.

    Args:
        raw: A dictionary that may contain factor information under various
            key names (``name`` / ``factor_name``, ``expression`` / ``formula``, etc.).

    Returns:
        A normalised factor dict, or ``None`` if mandatory fields are missing.
    """
    name = raw.get("name") or raw.get("factor_name") or raw.get("factor")
    expression = raw.get("expression") or raw.get("formula") or raw.get("expr")

    if not name:
        return None

    return {
        "name": str(name),
        "expression": str(expression) if expression else "",
        "ic_mean": raw.get("ic_mean"),
        "ic_ir": raw.get("ic_ir"),
        "description": raw.get("description", "Auto-discovered by RD-Agent"),
        "enabled": True,
    }


def _parse_factor_from_python(
    py_file: Path, source_code: str
) -> Optional[Dict[str, Any]]:
    """Attempt to extract a factor definition from a Python source file.

    Looks for common patterns in RD-Agent-generated factor code such as
    assignments to ``expr`` or ``expression`` variables and class-level
    ``name`` attributes.

    Args:
        py_file: Path to the Python file being inspected.
        source_code: The full text content of *py_file*.

    Returns:
        A factor dict in the standard schema, or ``None`` if nothing useful
        could be extracted.
    """
    factor_name = py_file.stem

    # Try to extract an expression assignment
    expr_match = re.search(
        r"""(?:expr|expression|formula)\s*=\s*['"](.+?)['"]""",
        source_code,
    )
    expression = expr_match.group(1) if expr_match else ""

    # Try to find a class-level name
    name_match = re.search(
        r"""(?:name|factor_name)\s*=\s*['"](.+?)['"]""",
        source_code,
    )
    if name_match:
        factor_name = name_match.group(1)

    # Try to find a description / docstring
    doc_match = re.search(r'"""(.+?)"""', source_code, re.DOTALL)
    description = (
        doc_match.group(1).strip().split("\n")[0]
        if doc_match
        else "Auto-discovered by RD-Agent"
    )

    return {
        "name": factor_name,
        "expression": expression,
        "ic_mean": None,
        "ic_ir": None,
        "description": description,
        "enabled": True,
    }


def _format_run_metadata(
    config: AppConfig,
    start_time: datetime,
    end_time: datetime,
    return_code: int,
    workspace_dir: str,
    factors_path: Optional[str],
) -> Dict[str, Any]:
    """Format metadata about a completed RD-Agent run.

    The returned dict is intended for logging, storage, or upload to shared
    storage so that downstream systems can audit what happened.

    Args:
        config: Application configuration used for the run.
        start_time: Timestamp when the run started.
        end_time: Timestamp when the run finished.
        return_code: Process exit code (``0`` = success).
        workspace_dir: Absolute path to the workspace.
        factors_path: Path to ``discovered_factors.yaml``, or ``None``.

    Returns:
        A JSON-serialisable dict containing run metadata including timing,
        status, model info, and discovered factor count.
    """
    duration = (end_time - start_time).total_seconds()

    factors_count = 0
    if factors_path is not None:
        try:
            with open(factors_path, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            factors_count = len(data.get("factors", []))
        except (OSError, yaml.YAMLError) as exc:
            logger.warning("Failed to count factors from {}: {}", factors_path, exc)

    return {
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "duration_seconds": round(duration, 2),
        "status": "success" if return_code == 0 else "failed",
        "return_code": return_code,
        "max_iterations": config.rdagent.max_iterations,
        "chat_model": config.llm.chat_model,
        "embedding_model": config.llm.embedding_model,
        "factors_discovered": factors_count,
        "factors_path": factors_path,
        "workspace_dir": workspace_dir,
    }
