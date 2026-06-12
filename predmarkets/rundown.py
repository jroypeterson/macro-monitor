"""Build the 3-lane prediction-market rundown and render it to plaintext,
Slack Block Kit, and a readable HTML panel.

Lanes: Aggregated (derived top-line) · Macro · Healthcare (pandemics/policy +
a biotech FDA-approval catalyst board). Block Kit follows the hard-won rules:
context blocks use elements[], sections stay <3000 chars, no rich_text.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .config import TRACKED, liquidity_flag
from .client import Resolved
from .history import Mover
from .discovery import NewMarket

# Compact aliases for the aggregated top-line (headline markets only).
_SHORT = {
    "recession": "Recession",
    "rate_cuts": "Fed cuts",
    "new_pandemic": "New pandemic",
    "rfk_out": "RFK out",
    "midterms": "Midterms",
}


def _pct(p: float) -> str:
    return f"{round(p * 100)}%"


def _vol(v: float) -> str:
    if v >= 1_000_000:
        return f"${v / 1_000_000:.1f}M"
    if v >= 1_000:
        return f"${v / 1_000:.0f}k"
    return f"${v:.0f}"


def _line(r: Resolved) -> str:
    """One rundown line for a resolved market (mrkdwn-safe)."""
    flag = liquidity_flag(r.volume)
    if not r.ok:
        return f"⚪ {r.label} — _no live market ({r.note})_"
    if r.is_binary:
        body = f"Yes {_pct(r.outcomes[0][1])}"
    else:
        top = r.outcomes[:2]
        body = " · ".join(f"{lbl} {_pct(p)}" for lbl, p in top)
    return f"{flag} *{r.label}* — {body}  ({_vol(r.volume)})"


def _move_line(m: Mover) -> str:
    arrow = "📈" if m.delta_pp > 0 else "📉"
    sign = "+" if m.delta_pp > 0 else "−"
    who = m.label if m.outcome.lower() == "yes" else f"{m.label} ({m.outcome})"
    return (f"{arrow} *{who}* — {round(m.old * 100)}% → {round(m.new * 100)}% "
            f"({sign}{abs(round(m.delta_pp))}pp {m.period})")


def _new_line(n: NewMarket) -> str:
    tag = "💊" if n.lane == "healthcare" else "📊"
    return f"{tag} *{n.title}* — {n.lead_label} {round(n.lead_prob * 100)}%  ({_vol(n.volume)})"


@dataclass
class Rundown:
    generated: datetime
    macro: list[Resolved] = field(default_factory=list)
    hc_pandemic: list[Resolved] = field(default_factory=list)
    hc_policy: list[Resolved] = field(default_factory=list)
    biotech: list[Resolved] = field(default_factory=list)
    aggregated: list[str] = field(default_factory=list)
    movers: list[Mover] = field(default_factory=list)
    new_markets: list[NewMarket] = field(default_factory=list)

    @property
    def live_count(self) -> int:
        return sum(1 for r in self._all() if r.ok)

    def _all(self) -> list[Resolved]:
        return self.macro + self.hc_pandemic + self.hc_policy + self.biotech


_POLICY_KEYS = {"rfk_out", "fda_commissioner"}


def build(resolved: list[Resolved], now: datetime | None = None, *,
          movers: list[Mover] | None = None,
          new_markets: list[NewMarket] | None = None) -> Rundown:
    now = now or datetime.now(timezone.utc)
    by_key = {r.key: r for r in resolved}
    rd = Rundown(generated=now, movers=list(movers or []), new_markets=list(new_markets or []))
    for r in resolved:
        if r.lane == "macro":
            rd.macro.append(r)
        elif r.biotech:
            rd.biotech.append(r)
        elif r.key in _POLICY_KEYS:
            rd.hc_policy.append(r)
        else:
            rd.hc_pandemic.append(r)

    # Aggregated top-line from headline markets (config order).
    for spec in TRACKED:
        if not spec.headline:
            continue
        r = by_key.get(spec.key)
        if not r or not r.ok:
            continue
        short = _SHORT.get(spec.key, spec.label)
        if r.is_binary:
            rd.aggregated.append(f"{short} {_pct(r.outcomes[0][1])}")
        else:
            lbl, p = r.outcomes[0]
            rd.aggregated.append(f"{short}: {lbl} {_pct(p)}")
    return rd


# ----- plaintext -----

def render_text(rd: Rundown) -> str:
    out = [f"Prediction Markets — {rd.generated:%Y-%m-%d}"]
    if rd.aggregated:
        out.append("  " + "  ·  ".join(rd.aggregated))
    if rd.movers:
        out.append("\nNOTABLE MOVES")
        out.extend("  " + _move_line(m).replace("*", "") for m in rd.movers)
    def block(title, rows):
        if rows:
            out.append(f"\n{title}")
            out.extend("  " + _line(r).replace("*", "") for r in rows)
    block("MACRO", rd.macro)
    block("HEALTHCARE — pandemics & public health", rd.hc_pandemic)
    block("HEALTHCARE — policy", rd.hc_policy)
    block("BIOTECH — FDA-approval catalysts (thin liquidity; directional)", rd.biotech)
    if rd.new_markets:
        out.append("\nNEWLY-OPENED RELEVANT MARKETS")
        out.extend("  " + _new_line(n).replace("*", "") for n in rd.new_markets)
    return "\n".join(out)


# ----- Slack Block Kit -----

def _section(md: str) -> dict:
    return {"type": "section", "text": {"type": "mrkdwn", "text": md[:2900]}}


def _section_lines(header: str, rows: list[Resolved]) -> list[dict]:
    if not rows:
        return []
    buf = f"*{header}*\n"
    blocks: list[dict] = []
    for r in rows:
        ln = _line(r) + "\n"
        if len(buf) + len(ln) > 2900:
            blocks.append(_section(buf.rstrip()))
            buf = ""
        buf += ln
    if buf.strip():
        blocks.append(_section(buf.rstrip()))
    return blocks


def build_blocks(rd: Rundown) -> list[dict]:
    blocks: list[dict] = [
        {"type": "header",
         "text": {"type": "plain_text", "text": f"🔮 Prediction Markets — {rd.generated:%b %d}"}},
        {"type": "context", "elements": [{"type": "mrkdwn",
         "text": "Forward-looking crowd odds · Polymarket · 🟢 >$250k  🟡 >$25k  🔴 thin (whale-sensitive)"}]},
    ]
    if rd.aggregated:
        blocks.append(_section("*At a glance:*  " + "   ".join(rd.aggregated)))
    if rd.movers:
        blocks.append(_section("*📈 Notable moves*\n" + "\n".join(_move_line(m) for m in rd.movers)))
    blocks.append({"type": "divider"})
    blocks += _section_lines("📊 Macro", rd.macro)
    blocks += _section_lines("🦠 Healthcare — pandemics & public health", rd.hc_pandemic)
    blocks += _section_lines("🏛️ Healthcare — policy", rd.hc_policy)
    blocks += _section_lines("💊 Biotech — FDA-approval catalysts", rd.biotech)
    if rd.biotech:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn",
            "text": "_Biotech approval markets are thin — read as directional, not calibrated._"}]})
    if rd.new_markets:
        blocks.append(_section("*🆕 Newly-opened relevant markets*\n"
                               + "\n".join(_new_line(n) for n in rd.new_markets)))
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn",
        "text": f"data: Polymarket Gamma · {rd.live_count} live markets · {rd.generated:%Y-%m-%d %H:%M UTC}"}]})
    return blocks


# ----- readable HTML panel -----

def _html_rows(rows: list[Resolved]) -> str:
    cells = []
    for r in rows:
        flag = liquidity_flag(r.volume)
        if not r.ok:
            cells.append(f'<tr><td>{r.label}</td><td colspan="2" class="dim">no live market ({r.note})</td></tr>')
            continue
        if r.is_binary:
            odds = f"Yes {_pct(r.outcomes[0][1])}"
        else:
            odds = " · ".join(f"{lbl} {_pct(p)}" for lbl, p in r.outcomes[:3])
        link = f'<a href="{r.url}" target="_blank">{r.label}</a>'
        cells.append(f'<tr><td>{flag} {link}</td><td>{odds}</td><td class="dim">{_vol(r.volume)}</td></tr>')
    return "\n".join(cells)


def render_html(rd: Rundown) -> str:
    def tbl(title, rows):
        if not rows:
            return ""
        return f"<h2>{title}</h2><table>{_html_rows(rows)}</table>"
    agg = ("<p class='agg'>" + "  ·  ".join(rd.aggregated) + "</p>") if rd.aggregated else ""
    movers_html = ""
    if rd.movers:
        rows = "\n".join(
            f"<tr><td>{'📈' if m.delta_pp > 0 else '📉'} {m.label}"
            f"{'' if m.outcome.lower() == 'yes' else ' (' + m.outcome + ')'}</td>"
            f"<td>{round(m.old * 100)}% → {round(m.new * 100)}%</td>"
            f"<td class='dim'>{'+' if m.delta_pp > 0 else '−'}{abs(round(m.delta_pp))}pp {m.period}</td></tr>"
            for m in rd.movers)
        movers_html = f"<h2>📈 Notable moves</h2><table>{rows}</table>"
    new_html = ""
    if rd.new_markets:
        rows = "\n".join(
            f'<tr><td>{"💊" if n.lane == "healthcare" else "📊"} '
            f'<a href="{n.url}" target="_blank">{n.title}</a></td>'
            f'<td>{n.lead_label} {round(n.lead_prob * 100)}%</td>'
            f'<td class="dim">{_vol(n.volume)}</td></tr>' for n in rd.new_markets)
        new_html = f"<h2>🆕 Newly-opened relevant markets</h2><table>{rows}</table>"
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Prediction Markets — macro_monitor</title>
<style>
 body{{font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;max-width:820px;margin:2rem auto;padding:0 1rem;color:#1a1a1a}}
 h1{{font-size:1.4rem;margin-bottom:.2rem}} h2{{font-size:1.05rem;margin:1.4rem 0 .4rem;border-bottom:1px solid #eee;padding-bottom:.2rem}}
 .sub{{color:#666;font-size:.85rem}} .agg{{background:#f5f7fa;border-radius:8px;padding:.6rem .8rem;font-weight:600}}
 table{{width:100%;border-collapse:collapse;margin:.2rem 0}} td{{padding:.3rem .4rem;border-bottom:1px solid #f2f2f2;vertical-align:top}}
 td:nth-child(2){{font-variant-numeric:tabular-nums}} .dim{{color:#888;font-size:.85rem;text-align:right}}
 a{{color:#0b65c2;text-decoration:none}} a:hover{{text-decoration:underline}} footer{{color:#999;font-size:.8rem;margin-top:2rem}}
</style></head><body>
<h1>🔮 Prediction Markets</h1>
<p class="sub">Forward-looking crowd odds · Polymarket · 🟢 &gt;$250k 🟡 &gt;$25k 🔴 thin · {rd.generated:%Y-%m-%d %H:%M UTC}</p>
{agg}
{movers_html}
{tbl("📊 Macro", rd.macro)}
{tbl("🦠 Healthcare — pandemics &amp; public health", rd.hc_pandemic)}
{tbl("🏛️ Healthcare — policy", rd.hc_policy)}
{tbl("💊 Biotech — FDA-approval catalysts <span class='sub'>(thin liquidity — directional)</span>", rd.biotech)}
{new_html}
<footer>{rd.live_count} live markets · source: Polymarket Gamma API · see PREDICTION_MARKETS.md</footer>
</body></html>"""
