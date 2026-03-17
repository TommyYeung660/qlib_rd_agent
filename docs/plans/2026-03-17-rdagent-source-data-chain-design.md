# RD-Agent Source Data Chain Design

**Problem**

The RD-Agent factor prompt contains a `The source data you can use:` section, but in the observed run it was empty. This caused the model to guess filenames such as `data.csv`, `stock_data.csv`, and `data.h5`, leading to repeated `FileNotFoundError` failures during factor implementation evaluation.

**Root Cause**

The wrapper-generated source-data chain does not match the upstream RD-Agent contract closely enough.

1. Upstream RD-Agent builds factor prompt source-data text from `get_data_folder_intro()`.
2. `get_data_folder_intro()` reads only `FACTOR_COSTEER_SETTINGS.data_folder_debug`.
3. The local wrapper generates full data successfully but may generate an empty debug slice.
4. When debug data is empty, the debug folder contains no describable files, so the prompt source-data section becomes blank.
5. The wrapper also writes `daily_pv_all.h5` / `daily_pv_debug.h5`, while upstream prompt generation expects the copied contract files `daily_pv.h5` and `README.md` inside the full/debug source-data folders.

**Constraints**

- This repository is developed on a Windows development machine without the target GPU runtime.
- The actual RD-Agent execution happens on another PC under WSL2.
- Fixes must therefore be local-repo changes that can be unit-tested without requiring the remote runtime host.

**Design**

The fix should happen in the local wrapper's data-preparation step.

1. Preserve current full-data generation.
2. Emit upstream-compatible artifacts into both source-data folders:
   - `daily_pv.h5`
   - `README.md`
3. When the intended debug slice is empty, fall back to a smaller subset derived from full data instead of leaving the debug folder empty.
4. Keep the existing `daily_pv_all.h5` / `daily_pv_debug.h5` files so current local debugging remains intact.

**Why This Design**

- It fixes the issue at the source of the blank prompt instead of patching downstream generated factor code.
- It aligns the local wrapper with upstream RD-Agent expectations.
- It can be verified with unit tests on the development machine.
- It does not require modifying the remote runtime host or the installed RD-Agent package.

**Testing Strategy**

Add unit tests around `src/runner/prepare_data.py` to verify:

1. A normal run writes upstream-compatible contract files.
2. An empty debug slice falls back to non-empty debug artifacts.
3. Existing short-circuit behavior still works when data already exists.

**Deployment Note**

The effective runtime behavior changes only after this repository update is deployed to the actual WSL2 execution machine. The Windows development machine validation here proves the wrapper logic and contracts, but the remote RD-Agent host must pull the updated repo before future runs will benefit from the fix.
