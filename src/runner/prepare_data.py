import sys
from pathlib import Path
import qlib
from qlib.data import D

# Add current directory to path to allow importing rdagent if needed
# But we assume this is run inside the conda env where rdagent is installed
try:
    from rdagent.components.coder.factor_coder.config import FACTOR_COSTEER_SETTINGS
except ImportError:
    print("Error: rdagent not installed in this environment.")
    sys.exit(1)


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

    # Check if files already exist
    if (target_dir / "daily_pv_all.h5").exists() and (
        target_dir_debug / "daily_pv_debug.h5"
    ).exists():
        print("✅ Data files already exist. Skipping generation.")
        return

    print("🚀 Initializing Qlib...")
    qlib.init(provider_uri=qlib_path)

    instruments = D.instruments()
    fields = ["$open", "$close", "$high", "$low", "$volume", "$factor"]

    # --- Generate Full Data ---
    print(f"📊 Generating full data to {target_dir}...")
    target_dir.mkdir(parents=True, exist_ok=True)

    # Fetch all data (similar to generate.py but using Qlib defaults)
    # generate.py used loc["2008-12-29":]
    data = D.features(instruments, fields, freq="day")
    if not data.empty:
        data = data.swaplevel().sort_index().sort_index()
        # Filter from 2008 if possible, or just take all if data is scarce
        try:
            data = data.loc["2008-01-01":]
        except KeyError:
            pass  # Keep all if slicing fails

        data.to_hdf(str(target_dir / "daily_pv_all.h5"), key="data")
        print("  - daily_pv_all.h5 saved")
    else:
        print("  ⚠️ Warning: No data found for full set!")

    # --- Generate Debug Data ---
    print(f"🐞 Generating debug data to {target_dir_debug}...")
    target_dir_debug.mkdir(parents=True, exist_ok=True)

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
        data_debug = data_debug.swaplevel().sort_index()
        # Take first 100 instruments
        instruments_debug = data_debug.index.get_level_values("instrument").unique()[
            :100
        ]
        data_debug = data_debug.loc[(slice(None), instruments_debug), :]
        data_debug = data_debug.swaplevel().sort_index()

        data_debug.to_hdf(str(target_dir_debug / "daily_pv_debug.h5"), key="data")
        print("  - daily_pv_debug.h5 saved")
    else:
        print("  ⚠️ Warning: No data found for debug set!")

    print("✨ Data preparation complete.")


if __name__ == "__main__":
    main()
