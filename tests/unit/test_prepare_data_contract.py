from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pandas as pd


def _make_feature_frame() -> pd.DataFrame:
    index = pd.MultiIndex.from_product(
        [
            ["AAA", "BBB"],
            pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]),
        ],
        names=["instrument", "datetime"],
    )
    return pd.DataFrame(
        {
            "$open": [10.0, 10.1, 10.2, 20.0, 20.1, 20.2],
            "$close": [10.5, 10.6, 10.7, 20.5, 20.6, 20.7],
            "$high": [10.7, 10.8, 10.9, 20.7, 20.8, 20.9],
            "$low": [9.9, 10.0, 10.1, 19.9, 20.0, 20.1],
            "$volume": [100, 110, 120, 200, 210, 220],
            "$factor": [1.0, 1.1, 1.2, 2.0, 2.1, 2.2],
        },
        index=index,
    )


def _load_prepare_data_module(monkeypatch, tmp_path: Path, feature_impl):
    full_dir = tmp_path / "full_source_data"
    debug_dir = tmp_path / "debug_source_data"

    fake_qlib = types.ModuleType("qlib")
    init_calls: list[str] = []

    def _fake_init(provider_uri: str) -> None:
        init_calls.append(provider_uri)

    fake_qlib.init = _fake_init

    fake_qlib_data = types.ModuleType("qlib.data")

    class _FakeD:
        @staticmethod
        def instruments():
            return ["AAA", "BBB"]

        @staticmethod
        def features(instruments, fields, **kwargs):
            return feature_impl(instruments, fields, **kwargs)

    fake_qlib_data.D = _FakeD

    factor_config = types.ModuleType("rdagent.components.coder.factor_coder.config")
    factor_config.FACTOR_COSTEER_SETTINGS = types.SimpleNamespace(
        data_folder=str(full_dir),
        data_folder_debug=str(debug_dir),
    )

    package_names = [
        "rdagent",
        "rdagent.components",
        "rdagent.components.coder",
        "rdagent.components.coder.factor_coder",
    ]
    for name in package_names:
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))

    monkeypatch.setitem(sys.modules, "qlib", fake_qlib)
    monkeypatch.setitem(sys.modules, "qlib.data", fake_qlib_data)
    monkeypatch.setitem(sys.modules, "rdagent.components.coder.factor_coder.config", factor_config)
    sys.modules.pop("src.runner.prepare_data", None)

    module = importlib.import_module("src.runner.prepare_data")
    return module, init_calls, full_dir, debug_dir


def _patch_fake_hdf(monkeypatch) -> None:
    def _fake_to_hdf(self, path, key="data", *args, **kwargs):
        self.to_pickle(path)

    def _fake_read_hdf(path, key="data", *args, **kwargs):
        return pd.read_pickle(path)

    monkeypatch.setattr(pd.DataFrame, "to_hdf", _fake_to_hdf)
    monkeypatch.setattr(pd, "read_hdf", _fake_read_hdf)


def test_prepare_data_writes_upstream_contract_artifacts(monkeypatch, tmp_path: Path) -> None:
    data = _make_feature_frame()
    _patch_fake_hdf(monkeypatch)

    def _feature_impl(instruments, fields, **kwargs):
        return data

    module, init_calls, full_dir, debug_dir = _load_prepare_data_module(monkeypatch, tmp_path, _feature_impl)
    monkeypatch.setattr(sys, "argv", ["prepare_data.py", str(tmp_path / "qlib_data")])

    module.main()

    assert init_calls == [str(tmp_path / "qlib_data")]
    assert (full_dir / "daily_pv.h5").exists()
    assert (full_dir / "README.md").exists()
    assert (debug_dir / "daily_pv.h5").exists()
    assert (debug_dir / "README.md").exists()


def test_prepare_data_falls_back_when_debug_slice_is_empty(monkeypatch, tmp_path: Path) -> None:
    data = _make_feature_frame()
    _patch_fake_hdf(monkeypatch)

    def _feature_impl(instruments, fields, **kwargs):
        if kwargs.get("start_time") == "2018-01-01":
            return pd.DataFrame()
        return data

    module, _, _, debug_dir = _load_prepare_data_module(monkeypatch, tmp_path, _feature_impl)
    monkeypatch.setattr(sys, "argv", ["prepare_data.py", str(tmp_path / "qlib_data")])

    module.main()

    debug_df = pd.read_hdf(debug_dir / "daily_pv.h5", key="data")
    assert not debug_df.empty


def test_prepare_data_backfills_contract_files_from_existing_hdf(monkeypatch, tmp_path: Path) -> None:
    data = _make_feature_frame()
    _patch_fake_hdf(monkeypatch)

    def _feature_impl(instruments, fields, **kwargs):
        raise AssertionError("feature generation should not run when cached source data exists")

    module, init_calls, full_dir, debug_dir = _load_prepare_data_module(monkeypatch, tmp_path, _feature_impl)
    full_dir.mkdir(parents=True, exist_ok=True)
    debug_dir.mkdir(parents=True, exist_ok=True)
    data.to_hdf(full_dir / "daily_pv_all.h5", key="data")
    data.to_hdf(debug_dir / "daily_pv_debug.h5", key="data")
    monkeypatch.setattr(sys, "argv", ["prepare_data.py", str(tmp_path / "qlib_data")])

    module.main()

    assert init_calls == []
    assert (full_dir / "daily_pv.h5").exists()
    assert (full_dir / "README.md").exists()
    assert (debug_dir / "daily_pv.h5").exists()
    assert (debug_dir / "README.md").exists()
