"""Tests for the market-chart parsers. The Ken French CSV logic is exercised with a
synthetic in-memory zip (no data dependency). Shiller/Damodaran parsers smoke-test only
when the (gitignored) data files are present locally.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from macro_monitor.market import charts as C

_MKT = Path(__file__).parent.parent / "market" / "data" / "latest"
_DAM = Path(__file__).parent.parent / "damodaran" / "data" / "latest"


def test_parse_ff_factors_multi_column(tmp_path):
    csv = (
        "Header prose line, with a comma.\n"
        "\n"
        ",Mkt-RF,SMB,HML,RF\n"
        "192607,   2.89,  -2.55,  -2.39,   0.22\n"
        "192608,   2.64,  -1.14,   3.81,   0.25\n"
        "\n"
        "  Annual Factors: January-December\n"
        ",Mkt-RF,SMB,HML,RF\n"
        "1926,   2.62,  -5.75,  -2.62,   3.27\n"
    )
    zp = tmp_path / "ff.zip"
    with zipfile.ZipFile(zp, "w") as z:
        z.writestr("F-F.csv", csv)
    df = C.parse_ff_factors(zp)
    assert list(df.columns) == ["Mkt-RF", "SMB", "HML", "RF"]
    assert len(df) == 2  # only the monthly block, annual section excluded
    assert df["Mkt-RF"].iloc[0] == pytest.approx(0.0289)  # 2.89% -> decimal


def test_parse_ff_factors_single_column_momentum(tmp_path):
    # Momentum file has a single column; header detection must accept ",Mom".
    csv = "prose\n\n,Mom\n192701,   0.57\n192702,  -1.50\n"
    zp = tmp_path / "mom.zip"
    with zipfile.ZipFile(zp, "w") as z:
        z.writestr("mom.csv", csv)
    df = C.parse_ff_factors(zp)
    assert list(df.columns) == ["Mom"]
    assert len(df) == 2


@pytest.mark.skipif(not (_MKT / "ie_data.xls").exists(), reason="Shiller file not downloaded")
def test_parse_shiller_smoke():
    df = C.parse_shiller()
    assert len(df) > 1000
    assert df["cape"].dropna().index.min().year <= 1900


@pytest.mark.skipif(not (_DAM / "histimpl.xls").exists(), reason="Damodaran file not downloaded")
def test_parse_damodaran_erp_smoke():
    df = C.parse_damodaran_erp()
    assert df.index.min().year <= 1961
    assert df["implied_erp"].dropna().iloc[-1] > 0
