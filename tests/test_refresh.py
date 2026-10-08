"""Pipeline tests on synthetic fixtures (no network, no real Zillow data)."""
import io
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from pipeline.refresh import PipelineError, TOP_N, run

MONTHS = ["2025-07-31", "2025-08-31", "2026-07-31", "2026-08-31"]
TODAY = date(2026, 10, 8)


def make_csv(n: int, value: float, months: list[str] = MONTHS, extra_col: str | None = None,
             drop_state: bool = False, dup_first: bool = False) -> str:
    ids = ["RegionID", "SizeRank", "RegionName", "RegionType"] + ([] if drop_state else ["StateName"])
    header = ids + ([extra_col] if extra_col else []) + months
    rows = [",".join(header), ",".join(["102001", "0", "United States", "country"] + ([] if drop_state else [""])
                                       + ([""] if extra_col else []) + [str(value)] * len(months))]
    for i in range(1, n + 1):
        region_id = 1 if dup_first and i == 2 else i
        cells = [str(region_id), str(i), f'"Metro {i}, ST"', "msa"] + ([] if drop_state else ["ST"])
        cells += ["x"] if extra_col else []
        cells += [str(value * (1 + i / 100)) for _ in months]
        rows.append(",".join(cells))
    return "\n".join(rows) + "\n"


def texts(n: int = 30, zhvi: float = 300_000, zori: float = 1_500, **kwargs: object) -> dict[str, str]:
    return {"zhvi": make_csv(n, zhvi, **kwargs), "zori": make_csv(n, zori)}


def test_happy_path_writes_all_outputs(tmp_path: Path) -> None:
    result = run(tmp_path, TODAY, texts(), min_joined=10)
    assert result.month == date(2026, 8, 31)
    assert len(result.table) == TOP_N
    # 300000 / (12 * 1500) = 16.67, scaled identically per metro so the ratio holds
    assert result.table["price_to_rent"].round(2).eq(16.67).all()
    assert result.table["price_to_rent_year_ago"].notna().all()
    for rel in ("data/price_to_rent.csv", "data/reconciliation.json", "data/badge.json",
                "assets/live-dark.svg", "assets/live-light.svg"):
        assert (tmp_path / rel).stat().st_size > 0


def test_rerun_is_byte_identical(tmp_path: Path) -> None:
    run(tmp_path, TODAY, texts(), min_joined=10)
    first = {p.name: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    run(tmp_path, TODAY, texts(), min_joined=10)
    second = {p.name: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert first == second


def test_new_upstream_column_fails_loudly(tmp_path: Path) -> None:
    with pytest.raises(PipelineError, match="zhvi: id columns changed|zhvi: unexpected column"):
        run(tmp_path, TODAY, texts(extra_col="Metro"), min_joined=10)
    assert not (tmp_path / "data").exists()  # nothing written on failure


def test_dropped_id_column_fails(tmp_path: Path) -> None:
    with pytest.raises(PipelineError, match="zhvi: id columns changed"):
        run(tmp_path, TODAY, texts(drop_state=True), min_joined=10)


def test_duplicate_region_fails(tmp_path: Path) -> None:
    with pytest.raises(PipelineError, match="RegionID must be unique"):
        run(tmp_path, TODAY, texts(dup_first=True), min_joined=10)


def test_empty_file_fails(tmp_path: Path) -> None:
    with pytest.raises(PipelineError, match="zori: file is empty"):
        run(tmp_path, TODAY, {"zhvi": make_csv(30, 300_000), "zori": ""}, min_joined=10)


def test_thin_join_fails(tmp_path: Path) -> None:
    with pytest.raises(PipelineError, match="join: expected at least 500"):
        run(tmp_path, TODAY, texts(), min_joined=500)


def test_stale_data_fails(tmp_path: Path) -> None:
    with pytest.raises(PipelineError, match="freshness"):
        run(tmp_path, date(2027, 6, 1), texts(), min_joined=10)


def test_large_metro_missing_rent_fails_instead_of_substituting(tmp_path: Path) -> None:
    zori_lines = make_csv(30, 1_500).splitlines()
    zori_lines = [line for line in zori_lines if not line.startswith("3,")]  # drop metro 3's rents
    with pytest.raises(PipelineError, match=r"coverage: .*Metro 3, ST"):
        run(tmp_path, TODAY, {"zhvi": make_csv(30, 300_000), "zori": "\n".join(zori_lines) + "\n"}, min_joined=10)


def edit_csv(text: str, region_id: int | None, month: str, value: str) -> str:
    """Set one cell (or a whole month column when region_id is None) in a fixture CSV."""
    frame = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
    rows = frame["RegionID"] != "102001" if region_id is None else frame["RegionID"] == str(region_id)
    frame.loc[rows, month] = value
    return frame.to_csv(index=False)


def test_corrupted_latest_month_fails_instead_of_falling_back(tmp_path: Path) -> None:
    zhvi = edit_csv(make_csv(30, 300_000), 5, "2026-08-31", "N/A")
    with pytest.raises(PipelineError, match=r"zhvi: expected a positive number, arrived 'N/A' for RegionID 5"):
        run(tmp_path, TODAY, {"zhvi": zhvi, "zori": make_csv(30, 1_500)}, min_joined=10)


def test_missing_year_ago_history_fails(tmp_path: Path) -> None:
    zori = edit_csv(make_csv(30, 1_500), 4, "2025-08-31", "")
    with pytest.raises(PipelineError, match=r"history: .*Metro 4, ST"):
        run(tmp_path, TODAY, {"zhvi": make_csv(30, 300_000), "zori": zori}, min_joined=10)


def test_year_ago_unit_error_fails_range_check(tmp_path: Path) -> None:
    zori = edit_csv(make_csv(30, 1_500), None, "2025-08-31", "18000")
    with pytest.raises(PipelineError, match=r"range: Aug 2025 price-to-rent"):
        run(tmp_path, TODAY, {"zhvi": make_csv(30, 300_000), "zori": zori}, min_joined=10)


def test_annual_rent_unit_error_fails_range_check(tmp_path: Path) -> None:
    # Rent arriving as an annual figure would make the ratio ~1.4, outside the plausible range.
    with pytest.raises(PipelineError, match=r"range: Aug 2026 price-to-rent"):
        run(tmp_path, TODAY, texts(zori=18_000), min_joined=10)
