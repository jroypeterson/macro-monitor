"""Computed series engine.

A computed series is derived in-process from one or more declared FRED
inputs. The forcing-function use case is healthcare employment as the
sum of NAICS 621 + 622 + 623 — BLS doesn't publish a single "Health
Care" series (their parent NAICS 62 includes social assistance / 624),
so we compute it ourselves.

The engine is intentionally narrow. Phase 1b ships only `sum_of`.
Later phases can add `diff`, `ratio`, `indexed_to_date`, `yoy_pct_of_sum`
as their use cases land. Keeping it small avoids the trap of building
a general-purpose formula language nobody validates against.
"""

from __future__ import annotations

import pandas as pd

SUPPORTED_METHODS = {"sum_of"}


def compute_series(
    method: str, inputs: dict[str, pd.Series], series_id: str
) -> pd.Series:
    """Compute a derived series from a {input_id: pd.Series} dict.

    Returns a pandas Series indexed by date with the result, NAMED with
    the synthetic `series_id`. If any input is missing for a given date,
    NaN propagates (we don't fabricate values across data gaps — the
    "October 2025 BLS gap" pattern that surfaced for CPI).
    """
    if method not in SUPPORTED_METHODS:
        raise ValueError(
            f"Unknown computed method {method!r}. "
            f"Supported: {sorted(SUPPORTED_METHODS)}"
        )
    if not inputs:
        return pd.Series(dtype=float, name=series_id)

    if method == "sum_of":
        return _sum_of(inputs, series_id)

    raise AssertionError("unreachable")  # SUPPORTED_METHODS gate above


def _sum_of(inputs: dict[str, pd.Series], series_id: str) -> pd.Series:
    """Element-wise sum across all input series, aligned by date index.

    NaN propagates: if any input is NaN on a given date, the sum is NaN.
    This is the conservative choice — we'd rather show "—" than fabricate
    a partial sum that looks like real data.
    """
    df = pd.DataFrame(inputs)
    # skipna=False so a missing input forces NaN, matching the philosophy
    # of "don't fabricate across data gaps."
    result = df.sum(axis=1, skipna=False)
    result.name = series_id
    return result.astype(float)
