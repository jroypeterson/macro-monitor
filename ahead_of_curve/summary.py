"""Key-takeaways summary for the gallery — a data-driven 'where are we in the cycle'
read computed from the latest data, in the spirit of Ellis's framework: real consumer
spending is the leading indicator, and its RATE OF CHANGE (accelerating vs decelerating)
is the tell. Everything here is computed at build time from the fetched series.
"""
from __future__ import annotations

import pandas as pd

from .charts import real_deflate, yoy_accel, yoy_pct


def _latest(s: pd.Series | None):
    if s is None:
        return None, None
    s = s.dropna()
    if s.empty:
        return None, None
    return s.index[-1], float(s.iloc[-1])


def _real(fetched: dict[str, pd.Series], num: str, den: str) -> pd.Series | None:
    a, b = fetched.get(num), fetched.get(den)
    if a is None or b is None or a.dropna().empty or b.dropna().empty:
        return None
    return real_deflate(a, b)


def _direction(accel_v: float | None, thresh: float = 0.3) -> str:
    if accel_v is None:
        return "n/a"
    if accel_v > thresh:
        return "accelerating"
    if accel_v < -thresh:
        return "decelerating"
    return "roughly steady"


def key_takeaways(fetched: dict[str, pd.Series]) -> tuple[str, list[str]]:
    """Return (headline, [bullet HTML strings]). Bullets use <b>…</b> for labels."""
    bullets: list[str] = []
    headline = ""

    # Leading indicator — real consumer spending (PCE), with its acceleration.
    pce = _real(fetched, "PCE", "PCEPI")
    if pce is not None:
        y, a = yoy_pct(pce), yoy_accel(pce)
        d, v = _latest(y)
        _, av = _latest(a)
        if d is not None:
            avg = float(y.mean())
            direction = _direction(av)
            rel = "above" if v >= avg else "below"
            headline = (
                f"Real consumer spending — the book's leading indicator — is growing "
                f"{v:.1f}% YoY ({d:%b %Y}) and {direction}, {rel} its long-run ~{avg:.1f}% pace."
            )
            accel_txt = f" ({av:+.1f}pp vs a year ago)" if av is not None else ""
            bullets.append(
                f"<b>Leading indicator — real consumer spending (PCE):</b> {v:.1f}% YoY "
                f"({d:%b %Y}), {direction}{accel_txt}; long-run average ~{avg:.1f}%."
            )

    # Capital spending — the lagging confirm.
    capex = _real(fetched, "PNFI", "GDPDEF")
    if capex is not None:
        d, v = _latest(yoy_pct(capex))
        _, av = _latest(yoy_accel(capex))
        if d is not None:
            bullets.append(
                f"<b>Capital spending (the follower):</b> {v:.1f}% YoY ({d:%b %Y}), "
                f"{_direction(av)}."
            )

    # Labor.
    emp_d, emp_v = _latest(yoy_pct(fetched["CE16OV"])) if fetched.get("CE16OV") is not None else (None, None)
    un_d, un_v = _latest(fetched.get("UNRATE"))
    if emp_d is not None:
        extra = f"; unemployment {un_v:.1f}%" if un_v is not None else ""
        bullets.append(f"<b>Labor:</b> employment {emp_v:.1f}% YoY ({emp_d:%b %Y}){extra}.")

    # Real hourly earnings.
    rae = _real(fetched, "AHETPI", "CPIAUCSL")
    if rae is not None:
        d, v = _latest(yoy_pct(rae))
        if d is not None:
            bullets.append(f"<b>Real hourly earnings:</b> {v:.1f}% YoY ({d:%b %Y}).")

    # Inflation & rates.
    parts: list[str] = []
    if fetched.get("CPIAUCSL") is not None:
        _, cv = _latest(yoy_pct(fetched["CPIAUCSL"]))
        if cv is not None:
            parts.append(f"CPI {cv:.1f}% YoY")
    _, fv = _latest(fetched.get("FEDFUNDS"))
    if fv is not None:
        parts.append(f"fed funds {fv:.1f}%")
    _, tv = _latest(fetched.get("GS10"))
    if tv is not None:
        parts.append(f"10-year {tv:.1f}%")
    if parts:
        bullets.append("<b>Inflation &amp; rates:</b> " + ", ".join(parts) + ".")

    # Sentiment.
    sd, sv = _latest(fetched.get("UMCSENT"))
    if sd is not None:
        bullets.append(f"<b>Consumer sentiment:</b> {sv:.1f} ({sd:%b %Y}, U. Michigan index).")

    return headline, bullets
