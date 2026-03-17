# RD-Agent Source Data Chain Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ensure RD-Agent always receives a non-empty source-data description by generating upstream-compatible source-data artifacts and falling back when the debug slice is empty.

**Architecture:** Keep the fix inside `src/runner/prepare_data.py`. Generate both the current local HDF5 outputs and the upstream-compatible `daily_pv.h5` plus `README.md` artifacts. If the requested debug slice has no rows, derive a reduced debug dataset from the full dataset instead of leaving the debug folder empty.

**Tech Stack:** Python, pandas, pytest, pathlib

---

### Task 1: Add failing regression tests for source-data artifacts

**Files:**
- Create: `tests/unit/test_prepare_data_contract.py`
- Modify: `src/runner/prepare_data.py`

**Step 1: Write the failing test**

Add tests that verify:
- full/debug folders contain `daily_pv.h5`
- full/debug folders contain `README.md`
- debug fallback produces a non-empty `daily_pv.h5` when the targeted debug slice is empty

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_prepare_data_contract.py -v`
Expected: FAIL because the current implementation does not create the upstream-compatible files or the debug fallback.

### Task 2: Implement minimal source-data contract fix

**Files:**
- Modify: `src/runner/prepare_data.py`
- Test: `tests/unit/test_prepare_data_contract.py`

**Step 1: Write minimal implementation**

Update `prepare_data.py` so that it:
- copies or writes `daily_pv.h5` into both source-data folders
- copies or writes `README.md` into both source-data folders
- uses a fallback debug subset when the configured time-range slice is empty

**Step 2: Run test to verify it passes**

Run: `pytest tests/unit/test_prepare_data_contract.py -v`
Expected: PASS

### Task 3: Verify no regression in existing runner contracts

**Files:**
- Test: `tests/unit/test_qlib_runner_contract.py`

**Step 1: Run focused existing tests**

Run: `pytest tests/unit/test_qlib_runner_contract.py -v`
Expected: PASS

**Step 2: Run combined targeted verification**

Run: `pytest tests/unit/test_prepare_data_contract.py tests/unit/test_qlib_runner_contract.py -v`
Expected: PASS

### Task 4: Summarize deployment implications

**Files:**
- Modify: `docs/plans/2026-03-17-rdagent-source-data-chain-design.md`

**Step 1: Confirm remote-runtime implication**

Document that the fix must be deployed to the actual WSL2 execution machine because that machine runs RD-Agent and owns the effective runtime behavior.
