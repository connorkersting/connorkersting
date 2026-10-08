"""Monthly profile pipeline: Zillow home values and rents -> price-to-rent chart.

fetch -> schema contract -> reconcile -> compute -> write outputs.

Any contract, reconciliation or range failure raises PipelineError before anything is
written, so a bad upstream month never replaces a good chart. Outputs are deterministic
for a given input (same month in, same bytes out), which keeps reruns idempotent and lets
the workflow commit only when the data actually changed.

Run from the repo root:  uv run python -m pipeline.refresh
"""
from __future__ import annotations

import io
import json
import sys
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from pipeline.chart import render_chart

BASE_URL = "https://files.zillowstatic.com/research/public_csvs"
SOURCES: dict[str, str] = {
    # Same files as connorkersting/us-housing-buy-vs-rent (data-prep/refresh_raw.R).
    "zhvi": f"{BASE_URL}/zhvi/Metro_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv",
    "zori": f"{BASE_URL}/zori/Metro_zori_uc_sfrcondomfr_sm_month.csv",
}
ID_COLUMNS = ["RegionID", "SizeRank", "RegionName", "RegionType", "StateName"]
TOP_N = 20
MIN_JOINED = 200  # metros with both values in the chosen month; ~600 is normal
MAX_AGE_DAYS = 150  # Zillow publishes monthly; older than ~5 months means it stalled
RATIO_RANGE = (5.0, 60.0)  # outside this, a unit or join error is likelier than reality


class PipelineError(RuntimeError):
    """A check failed. The message names the source, what was expected and what arrived."""


@dataclass(frozen=True)
class Result:
    month: date
    table: pd.DataFrame
    reconciliation: dict[str, int | str]
    checks_passed: int


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "connorkersting-profile-pipeline"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8")


def load_source(name: str, text: str) -> pd.DataFrame:
    """Parse one Zillow CSV and enforce its contract. Returns a long table."""
    if not text.strip():
        raise PipelineError(f"{name}: file is empty")
    # Only truly empty cells count as missing. pandas' defaults would also turn "N/A", "null",
    # "NaN" etc. into NaN, which would hide upstream corruption from the value check below.
    raw = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False, na_values=[""])
    arrived = list(raw.columns[: len(ID_COLUMNS)])
    if arrived != ID_COLUMNS:
        raise PipelineError(f"{name}: id columns changed. expected {ID_COLUMNS}, arrived {arrived}")
    for column in raw.columns[len(ID_COLUMNS):]:
        try:
            date.fromisoformat(column)
        except ValueError:
            raise PipelineError(
                f"{name}: unexpected column {column!r}. expected only YYYY-MM-DD month columns "
                f"after {ID_COLUMNS[-1]}; decide whether to include it before rerunning"
            ) from None
    if len(raw.columns) == len(ID_COLUMNS):
        raise PipelineError(f"{name}: no month columns arrived")
    if raw["RegionID"].duplicated().any():
        dupes = raw.loc[raw["RegionID"].duplicated(), "RegionID"].head(3).tolist()
        raise PipelineError(f"{name}: RegionID must be unique per row; duplicates arrived, e.g. {dupes}")
    for column in ("RegionID", "SizeRank"):
        bad = pd.to_numeric(raw[column], errors="coerce").isna() & raw[column].notna()
        if bad.any():
            raise PipelineError(f"{name}: {column} expected integers, arrived {raw.loc[bad, column].iloc[0]!r}")

    melted = raw.loc[raw["RegionType"] == "msa"].melt(id_vars=ID_COLUMNS, var_name="month", value_name="raw")
    parsed = pd.to_numeric(melted["raw"], errors="coerce")
    # Empty cells are normal (series start at different dates). A non-empty cell that is not a
    # positive number is corruption: fail rather than let it fall back to an older month.
    malformed = melted["raw"].notna() & (parsed.isna() | (parsed <= 0))
    if malformed.any():
        row = melted.loc[malformed].iloc[0]
        raise PipelineError(
            f"{name}: expected a positive number, arrived {row['raw']!r} for RegionID {row['RegionID']} "
            f"in {row['month']} ({int(malformed.sum())} malformed cells)"
        )
    long = (
        melted.assign(
            RegionID=lambda d: d["RegionID"].astype("int64"),
            SizeRank=lambda d: d["SizeRank"].astype("int64"),
            month=lambda d: pd.to_datetime(d["month"]).dt.date,
            value=parsed,
        )
        .drop(columns="raw")
        .dropna(subset=["value"])
    )
    if long.empty:
        raise PipelineError(f"{name}: no metro (RegionType == 'msa') rows with values")
    return long


def compute(zhvi: pd.DataFrame, zori: pd.DataFrame, today: date, min_joined: int = MIN_JOINED) -> Result:
    checks = 0
    keys = ["RegionID", "month"]
    joined = zhvi.merge(
        zori[keys + ["value"]].rename(columns={"value": "zori"}), on=keys, how="inner"
    ).rename(columns={"value": "zhvi"})

    per_month = joined.groupby("month")["RegionID"].nunique()
    usable = per_month[per_month >= min_joined]
    if usable.empty:
        best = int(per_month.max()) if not per_month.empty else 0
        raise PipelineError(
            f"join: expected at least {min_joined} metros with both a home value and a rent in some "
            f"month, arrived at most {best}. Check RegionID alignment between zhvi and zori"
        )
    checks += 1
    month = max(usable.index)
    age = (today - month).days
    if age > MAX_AGE_DAYS:
        raise PipelineError(f"freshness: latest usable month is {month} ({age} days old), expected <= {MAX_AGE_DAYS}")
    checks += 1

    year_ago = date(month.year - 1, month.month, 1)
    current = joined.loc[joined["month"] == month]
    # The chart claims "the N largest metros", so pick them from the home-value file's own
    # SizeRank and require every one to be present; never let the N+1th quietly fill a gap.
    largest = (
        zhvi[["RegionID", "SizeRank", "RegionName"]].drop_duplicates("RegionID").nsmallest(TOP_N, "SizeRank")
    )
    missing = largest.loc[~largest["RegionID"].isin(current["RegionID"]), "RegionName"].tolist()
    if missing:
        raise PipelineError(f"coverage: the {TOP_N} largest metros must all have both values in {month}; missing {missing}")
    checks += 1
    current = current.loc[current["RegionID"].isin(largest["RegionID"])]
    prior = (
        joined.loc[pd.to_datetime(joined["month"]).dt.to_period("M") == pd.Period(year_ago, "M")]
        .assign(price_to_rent_year_ago=lambda d: d["zhvi"] / (12 * d["zori"]))
        [["RegionID", "price_to_rent_year_ago"]]
    )
    table = (
        current.assign(price_to_rent=lambda d: d["zhvi"] / (12 * d["zori"]))
        .nsmallest(TOP_N, "SizeRank")
        .merge(prior, on="RegionID", how="left")
        .loc[:, ["month", "RegionID", "RegionName", "StateName", "SizeRank", "zhvi", "zori",
                 "price_to_rent", "price_to_rent_year_ago"]]
        .rename(columns={"RegionID": "region_id", "RegionName": "metro", "StateName": "state",
                         "SizeRank": "size_rank"})
        .sort_values(["price_to_rent", "region_id"], ascending=[False, True])
        .reset_index(drop=True)
    )
    if len(table) != TOP_N:
        raise PipelineError(f"compute: expected {TOP_N} metros in the chart, arrived {len(table)}")
    checks += 1
    # The legend promises a year-over-year comparison, so every charted metro needs history.
    no_history = table.loc[table["price_to_rent_year_ago"].isna(), "metro"].tolist()
    if no_history:
        raise PipelineError(f"history: no {year_ago:%b %Y} value for {no_history}; the chart compares against it")
    checks += 1
    lo, hi = RATIO_RANGE
    for column, label in (("price_to_rent", f"{month:%b %Y}"), ("price_to_rent_year_ago", f"{year_ago:%b %Y}")):
        out_of_range = table.loc[~table[column].between(lo, hi), ["metro", column]]
        if not out_of_range.empty:
            row = out_of_range.iloc[0]
            raise PipelineError(
                f"range: {label} price-to-rent expected between {lo} and {hi}, arrived {row[column]:.1f} "
                f"for {row['metro']}. Likely a unit or join error"
            )
        checks += 1
    if table[["zhvi", "zori", "price_to_rent"]].isna().any().any():
        raise PipelineError("compute: nulls arrived in zhvi, zori or price_to_rent for charted metros")
    checks += 1

    reconciliation: dict[str, int | str] = {
        "month": month.isoformat(),
        "zhvi_metros": int(zhvi["RegionID"].nunique()),
        "zori_metros": int(zori["RegionID"].nunique()),
        "joined_metros_in_month": int(per_month[month]),
        "zhvi_only_metros": int(len(set(zhvi["RegionID"]) - set(zori["RegionID"]))),
        "zori_only_metros": int(len(set(zori["RegionID"]) - set(zhvi["RegionID"]))),
        "charted_metros": int(len(table)),
        "charted_with_year_ago": int(table["price_to_rent_year_ago"].notna().sum()),
    }
    return Result(month=month, table=table, reconciliation=reconciliation, checks_passed=checks)


def write_outputs(result: Result, root: Path, source_checks: int) -> None:
    """Write CSV, reconciliation, badge and both SVGs. Deterministic for a given result."""
    checks = result.checks_passed + source_checks
    data_dir, assets_dir = root / "data", root / "assets"
    data_dir.mkdir(exist_ok=True)
    assets_dir.mkdir(exist_ok=True)
    table = result.table.assign(
        zhvi=lambda d: d["zhvi"].round(0).astype("int64"),
        zori=lambda d: d["zori"].round(0).astype("int64"),
        price_to_rent=lambda d: d["price_to_rent"].round(2),
        price_to_rent_year_ago=lambda d: d["price_to_rent_year_ago"].round(2),
    )
    outputs: dict[Path, str] = {
        data_dir / "price_to_rent.csv": table.to_csv(index=False, lineterminator="\n"),
        data_dir / "reconciliation.json": json.dumps({**result.reconciliation, "checks_passed": checks}, indent=2) + "\n",
        data_dir / "badge.json": json.dumps({
            "schemaVersion": 1,
            "label": "live data",
            "message": f"{result.month:%b %Y} · {len(table)} metros · {checks} checks passed",
            "color": "2ea043",
        }) + "\n",
    }
    for theme in ("dark", "light"):
        outputs[assets_dir / f"live-{theme}.svg"] = render_chart(table, result.month, theme)
    for path, content in outputs.items():
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(content, encoding="utf-8", newline="\n")
        tmp.replace(path)


def run(root: Path, today: date, texts: dict[str, str] | None = None, min_joined: int = MIN_JOINED) -> Result:
    texts = texts or {name: fetch(url) for name, url in SOURCES.items()}
    frames = {name: load_source(name, text) for name, text in texts.items()}
    # Per source: non-empty, id columns, month columns, at least one month, unique RegionID,
    # integer ids (RegionID + SizeRank counted once), well-formed positive values, metro rows present.
    source_checks = 8 * len(frames)
    result = compute(frames["zhvi"], frames["zori"], today, min_joined)
    write_outputs(result, root, source_checks)
    return result


def main() -> None:
    try:
        result = run(Path("."), date.today())
    except PipelineError as error:
        print(f"PIPELINE FAILED: {error}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(result.reconciliation, indent=2))


if __name__ == "__main__":
    main()
