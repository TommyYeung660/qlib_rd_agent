import sys
from pathlib import Path

import pandas as pd
import qlib
from qlib.data import D

# Add current directory to path to allow importing rdagent if needed
# But we assume this is run inside the conda env where rdagent is installed
try:
    from rdagent.components.coder.factor_coder.config import FACTOR_COSTEER_SETTINGS
except ImportError:
    print("Error: rdagent not installed in this environment.")
    sys.exit(1)


_DAILY_PV_README = """# How to read files.
For example, if you want to read `daily_pv.h5`
```Python
import pandas as pd
df = pd.read_hdf("daily_pv.h5", key="data")
```
NOTE: key is always "data" for all hdf5 files.

# Here is a short description about the data

| Filename      | Description                           |
| ------------- | ------------------------------------- |
| "daily_pv.h5" | Adjusted daily price and volume data. |

## Daily price and volume data
$open: open price of the stock on that day.
$close: close price of the stock on that day.
$high: high price of the stock on that day.
$low: low price of the stock on that day.
$volume: volume of the stock on that day.
$factor: factor value of the stock on that day.
"""


def _write_contract_readme(target_dir: Path) -> None:
    (target_dir / "README.md").write_text(_DAILY_PV_README, encoding="utf-8")


def _write_dataset_bundle(df: pd.DataFrame, target_dir: Path, legacy_name: str) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    df.to_hdf(str(target_dir / legacy_name), key="data")
    df.to_hdf(str(target_dir / "daily_pv.h5"), key="data")
    _write_contract_readme(target_dir)


def _backfill_contract_from_existing(target_dir: Path, legacy_name: str) -> bool:
    legacy_path = target_dir / legacy_name
    if not legacy_path.exists():
        return False

    contract_path = target_dir / "daily_pv.h5"
    if not contract_path.exists():
        pd.read_hdf(legacy_path, key="data").to_hdf(str(contract_path), key="data")
    _write_contract_readme(target_dir)
    return True


def _prepare_full_data(data: pd.DataFrame) -> pd.DataFrame:
    prepared = data.swaplevel().sort_index()
    try:
        prepared = prepared.loc["2008-01-01":]
    except KeyError:
        pass
    return prepared.sort_index()


def _select_debug_instruments(data: pd.DataFrame) -> pd.Index:
    return data.index.get_level_values("instrument").unique()[:100]


def _prepare_debug_data(data_debug: pd.DataFrame, full_data: pd.DataFrame) -> pd.DataFrame:
    prepared = data_debug.swaplevel().sort_index()
    instruments_debug = _select_debug_instruments(full_data if not full_data.empty else prepared)
    prepared = prepared.swaplevel().loc[instruments_debug].swaplevel().sort_index()
    return prepared


def _build_debug_fallback(full_data: pd.DataFrame) -> pd.DataFrame:
    if full_data.empty:
        return full_data

    fallback = full_data.swaplevel().loc[_select_debug_instruments(full_data)].swaplevel().sort_index()
    debug_dates = fallback.index.get_level_values("datetime").unique()
    if len(debug_dates) > 504:
        fallback = fallback.loc[debug_dates[-504]:]
    return fallback


def main():
    if len(sys.argv) < 2:
        print("Usage: python prepare_data.py <qlib_data_path>")
        sys.exit(1)

    qlib_path = sys.argv[1]

    # Resolve target paths from RD-Agent settings
    # These settings usually default to relative paths like "git_ignore_folder/..."
    # We must ensure they are absolute or relative to the CURRENT working directory
    # which will be set by the caller (workspace_dir)
    target_dir = Path(FACTOR_COSTEER_SETTINGS.data_folder).resolve()
    target_dir_debug = Path(FACTOR_COSTEER_SETTINGS.data_folder_debug).resolve()

    print(f"Target Data Dir: {target_dir}")
    print(f"Target Debug Dir: {target_dir_debug}")

    target_dir.mkdir(parents=True, exist_ok=True)
    target_dir_debug.mkdir(parents=True, exist_ok=True)

    # Check if files already exist
    if (target_dir / "daily_pv_all.h5").exists() and (
        target_dir_debug / "daily_pv_debug.h5"
    ).exists():
        _backfill_contract_from_existing(target_dir, "daily_pv_all.h5")
        _backfill_contract_from_existing(target_dir_debug, "daily_pv_debug.h5")
        print("✅ Data files already exist. Skipping generation.")
        return

    print("🚀 Initializing Qlib...")
    qlib.init(provider_uri=qlib_path)

    instruments = D.instruments()
    fields = ["$open", "$close", "$high", "$low", "$volume", "$factor"]

    # --- Generate Full Data ---
    print(f"📊 Generating full data to {target_dir}...")

    # Fetch all data (similar to generate.py but using Qlib defaults)
    # generate.py used loc["2008-12-29":]
    data = D.features(instruments, fields, freq="day")
    if not data.empty:
        data = _prepare_full_data(data)
        _write_dataset_bundle(data, target_dir, "daily_pv_all.h5")
        print("  - daily_pv_all.h5 saved")
        print("  - daily_pv.h5 saved")
        print("  - README.md saved")
    else:
        print("  ⚠️ Warning: No data found for full set!")

    # --- Generate Debug Data ---
    print(f"🐞 Generating debug data to {target_dir_debug}...")

    # Fetch smaller subset (2018-2020)
    try:
        data_debug = D.features(
            instruments,
            fields,
            start_time="2018-01-01",
            end_time="2020-12-31",
            freq="day",
        )
    except Exception:
        # Fallback to whatever is available if date range invalid
        data_debug = D.features(instruments, fields, freq="day")

    if not data_debug.empty:
        data_debug = _prepare_debug_data(data_debug, data)
    else:
        print("  ⚠️ Warning: No data found for debug set! Falling back to full-data subset.")
        data_debug = _build_debug_fallback(data)

    if not data_debug.empty:
        _write_dataset_bundle(data_debug, target_dir_debug, "daily_pv_debug.h5")
        print("  - daily_pv_debug.h5 saved")
        print("  - daily_pv.h5 saved")
        print("  - README.md saved")
    else:
        print("  ⚠️ Warning: No data found for debug fallback set!")

    print("✨ Data preparation complete.")


if __name__ == "__main__":
    main()
