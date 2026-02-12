"""Post-processing patch for RD-Agent generated factor code.

The RD-Agent LLM generates factor code with hardcoded Qlib initialization paths
like:
    qlib.init(provider_uri="~/.qlib/qlib_data/cn_data", region="cn")
    qlib.init(provider_uri="/path/to/qlib_data/cn_data", region="cn")

These hardcoded paths don't match the actual Qlib data location configured in
the environment via QLIB_DATA_PATH. This module patches such files to use the
environment variable instead.

Patching strategy:
    1. Scan generated Python files for qlib.init() calls
    2. Replace provider_uri with os.environ['QLIB_DATA_PATH']
    3. Ensure os is imported
"""

import os
import re
from pathlib import Path
from typing import List

from loguru import logger


def patch_qlib_init_in_file(file_path: Path, qlib_data_path: str) -> bool:
    """Patch qlib.init() calls in a single Python file.

    Replaces hardcoded provider_uri with environment variable reference.

    Args:
        file_path: Path to Python file to patch.
        qlib_data_path: The correct Qlib data path (for validation).

    Returns:
        True if file was modified, False if no changes needed.
    """
    try:
        content = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("Cannot read {}: {}", file_path, exc)
        return False

    original = content

    # --- Pattern 1: qlib.init with explicit provider_uri (most common) ---
    # Matches: qlib.init(provider_uri="...", ...)
    # Also:    qlib.init(provider_uri='...', ...)
    # Also:    qlib.init(provider_uri=path_variable, ...)
    pattern_provider = re.compile(
        r'qlib\.init\s*\(\s*provider_uri\s*=\s*["\']?[^"\']+["\']?\s*,',
        re.MULTILINE,
    )

    if pattern_provider.search(content):
        # Replace with environment variable version
        def replacer(match):
            # Extract the part before provider_uri and after the opening (
            prefix = match.group(0)[: match.group(0).find("provider_uri")]
            # Return replacement with env variable
            return 'qlib.init(\n        provider_uri=os.environ.get("QLIB_DATA_PATH", "'
            +qlib_data_path
            +'"),\n        '

        content = pattern_provider.sub(replacer, content)

    # --- Pattern 2: Ensure os is imported if we made changes ---
    if content != original:
        if "import os" not in content:
            # Add import at the top (after any __future__ imports)
            lines = content.split("\n")
            insert_idx = 0
            for i, line in enumerate(lines):
                if line.startswith("from __future__"):
                    insert_idx = i + 1
            lines.insert(insert_idx, "import os")
            content = "\n".join(lines)

        # Write back
        try:
            file_path.write_text(content, encoding="utf-8")
            logger.info("Patched {}", file_path)
            return True
        except OSError as exc:
            logger.error("Failed to write {}: {}", file_path, exc)
            return False

    return False


def patch_generated_code_in_workspace(workspace_dir: str, qlib_data_path: str) -> int:
    """Patch all generated Python files in an RD-Agent workspace.

    Recursively scans the workspace for .py files and patches qlib.init() calls
    to use the configured QLIB_DATA_PATH instead of hardcoded paths.

    Args:
        workspace_dir: Path to RD-Agent workspace directory.
        qlib_data_path: The correct Qlib data path.

    Returns:
        Number of files patched.
    """
    workspace = Path(workspace_dir)
    if not workspace.is_dir():
        logger.warning("Workspace directory not found: {}", workspace_dir)
        return 0

    patched_count = 0
    for py_file in workspace.rglob("*.py"):
        # Skip this script itself if it somehow exists in workspace
        if py_file.name == "patch_generated_code.py":
            continue

        if patch_qlib_init_in_file(py_file, qlib_data_path):
            patched_count += 1

    logger.info("Patched {} files in workspace", patched_count)
    return patched_count


if __name__ == "__main__":
    # Simple CLI for testing
    import sys

    if len(sys.argv) < 3:
        print("Usage: python patch_generated_code.py <workspace_dir> <qlib_data_path>")
        sys.exit(1)

    ws_dir = sys.argv[1]
    qlib_path = sys.argv[2]

    count = patch_generated_code_in_workspace(ws_dir, qlib_path)
    print(f"✅ Patched {count} files")
