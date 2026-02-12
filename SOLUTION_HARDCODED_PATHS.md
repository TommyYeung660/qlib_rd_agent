"""
SOLUTION: Fix Hardcoded Qlib Data Path in RD-Agent Generated Code
===================================================================

PROBLEM
-------
RD-Agent's LLM generates factor code with hardcoded paths like:
  - qlib.init(provider_uri="~/.qlib/qlib_data/cn_data", region="cn")
  - qlib.init(provider_uri="/path/to/qlib_data/cn_data", region="cn")

These paths don't match the actual QLIB_DATA_PATH configured in the environment,
causing:
  ValueError: instrument: {'__DEFAULT_FREQ': '/path/to/qlib_data/cn_data'} 
              does not contain data for day

ROOT CAUSE
----------
1. RD-Agent's internal prompts instruct the LLM to use hardcoded default paths
2. We cannot easily modify RD-Agent's system prompts (it's in the library)
3. The environment variable QLIB_DATA_PATH is set but not used by generated code
4. The generated code runs INSIDE the RD-Agent subprocess, so we can't intercept it

SOLUTION STRATEGY: Symlink Approach
-----------------------------------
Instead of patching generated code (which is complex and fragile), create symlinks
from common hardcoded paths to the actual QLIB_DATA_PATH. This way:

1. LLM generates: qlib.init(provider_uri="~/.qlib/qlib_data/cn_data")
2. The path ~/.qlib/qlib_data/cn_data is a symlink → actual QLIB_DATA_PATH
3. Qlib resolves the symlink and finds the correct data
4. No code modification needed - transparent to RD-Agent

IMPLEMENTATION
---------------

File: src/runner/qlib_runner.py
  - Added _setup_qlib_data_symlinks(config) function (lines 198-240)
  - Creates symlinks from common hardcoded paths to actual data
  - Called in run_rdagent() step 2.5 (line 362)
  - Handles both home directory (~/.qlib/) and absolute paths (/path/to/)
  - Gracefully handles permission errors (doesn't fail if symlink can't be created)

File: src/runner/patch_generated_code.py (BACKUP OPTION)
  - Alternative approach: patch generated Python files directly
  - Used only if symlink approach doesn't work
  - Can be integrated into post-processing later if needed

File: src/runner/patch_monitor.py (BACKUP OPTION)
  - Monitors workspace for new generated files
  - Patches them in real-time as they're created
  - Currently unused but available for future use

SYMLINK TARGETS CREATED
-----------------------
The _setup_qlib_data_symlinks() function creates symlinks at:

1. ~/.qlib/qlib_data/cn_data → {actual_path}
   (Most common path in default Qlib installations)

2. ~/.qlib/qlib_data → {actual_path}
   (In case LLM uses a less specific path)

3. /path/to/qlib_data/cn_data → {actual_path}
   (In case LLM uses absolute paths - limited by permissions)

4. /path/to/qlib_data → {actual_path}
   (Less specific absolute path variant)

EXECUTION FLOW
---------------
Previous: RD-Agent → ❌ ValueError (hardcoded path doesn't exist)
New:      RD-Agent Subprocess
            ↓
          qlib.init(provider_uri="~/.qlib/qlib_data/cn_data")
            ↓
          OS resolves symlink
            ↓
          Actual QLIB_DATA_PATH
            ↓
          ✅ Data found, RD-Agent continues

ROBUSTNESS
----------
✅ Transparent - no changes to generated code
✅ Handles symlink creation errors gracefully
✅ Updates existing symlinks if they point to wrong location
✅ Works with both relative (~/) and absolute paths
✅ Supported on Windows, Linux, macOS (via pathlib)

TESTING STRATEGY
---------------
1. Verify symlink creation:
   - Check ~/.qlib/qlib_data/cn_data exists and points to correct path
   
2. Test with RD-Agent run:
   - Run: python -m src.main run
   - Monitor for "does not contain data" errors
   - Check logs for symlink creation messages
   
3. Verify factor discovery:
   - Check discovered_factors.yaml is generated
   - Confirm factors are extracted correctly

ERROR HANDLING
--------------
If symlink approach fails:
1. Fall back to patch_generated_code.py approach
   - This patches Python files after generation
   - Currently not integrated but available

2. Manually create symlinks:
   - User can manually: ln -s /actual/path ~/.qlib/qlib_data/cn_data
   - Or copy data to expected location

FUTURE IMPROVEMENTS
-------------------
1. Could also try setting QLIB_DATA_PATH in .qlib/conf.yaml
2. Could patch RD-Agent's prompt if we fork the library
3. Could create a custom qlib.init() wrapper in prepare_data.py
"""

# This is documentation, not code.
# Save as: SOLUTION_HARDCODED_PATHS.md
