"""Tests for the prediction-market lane (predmarkets/).

Network-free: the Polymarket client is exercised via monkeypatched
search/fetch, and the rundown/blocks/html are validated against Slack's
Block Kit constraints (same rules that bit podcast_triage: context→elements[],
sections <3000 chars, <=50 blocks, no rich_text).
"""
from __future__ import annotations

import pytest

from datetime import datetime, timezone

from macro_monitor.predmarkets import client, config, rundown as RD
from macro_monitor.predmarkets import history as HIST
from macro_monitor.predmarkets import discovery as DISC
from macro_monitor.predmarkets.client import Resolved

_UTC = timezone.utc


# ---- client parsing ----

def _binary_event(title, slug, vol, yes):
    return {"title": title, "slug": slug, "closed": False, "volume": vol,
            "endDate": "2026-12-31T00:00:00Z",
            "markets": [{"outcomes": '["Yes","No"]',
                         "outcomePrices": f'["{yes}","{1 - yes:.2f}"]', "closed": False}]}


def _multi_event(title, slug, vol, pairs):
    mk = [{"groupItemTitle": lbl, "outcomes": '["Yes","No"]',
           "outcomePrices": f'["{p}","{1 - p:.2f}"]', "closed": False} for lbl, p in pairs]
    return {"title": title, "slug": slug, "closed": False, "volume": vol,
            "endDate": "2026-12-31T00:00:00Z", "markets": mk}


def test_normalize_binary():
    ev = _binary_event("US recession by end of 2026?", "us-recession", 1_500_000, 0.18)
    out = client._normalize(ev)
    assert out == [("Yes", 0.18)]


def test_normalize_multi_sorted_desc():
    ev = _multi_event("How many Fed rate cuts in 2026?", "cuts", 34_000_000,
                      [("0 (0 bps)", 0.77), ("1 (25 bps)", 0.14), ("2 (50 bps)", 0.04)])
    out = client._normalize(ev)
    assert out[0] == ("0 (0 bps)", 0.77)
    assert [p for _, p in out] == sorted([p for _, p in out], reverse=True)


def test_resolve_picks_highest_volume_match(monkeypatch):
    spec = config.TrackedMarket("recession", "macro", "recession", "US recession", "US recession")
    monkeypatch.setattr(client, "search_events", lambda q, limit=20: [
        {"title": "US recession by end of 2026?", "slug": "lowvol"},
        {"title": "US recession by end of 2026?", "slug": "hivol"},
        {"title": "Soccer recession joke", "slug": "nope"},  # filtered by match
    ])
    fulls = {"lowvol": _binary_event("US recession by end of 2026?", "lowvol", 100, 0.20),
             "hivol": _binary_event("US recession by end of 2026?", "hivol", 9_000, 0.18)}
    monkeypatch.setattr(client, "fetch_event", lambda slug: fulls.get(slug))
    r = client.resolve(spec)
    assert r.ok and r.is_binary
    assert r.volume == 9_000 and r.outcomes == [("Yes", 0.18)]
    assert r.url.endswith("/hivol")


def test_resolve_not_found(monkeypatch):
    spec = config.TrackedMarket("x", "macro", "q", "no-such-title", "X")
    monkeypatch.setattr(client, "search_events", lambda q, limit=20: [{"title": "other", "slug": "s"}])
    r = client.resolve(spec)
    assert not r.ok and r.note == "not found"


def test_resolve_survives_network_error(monkeypatch):
    spec = config.TrackedMarket("x", "macro", "q", "m", "X")
    def boom(q, limit=20):
        raise client.requests.RequestException("dns")
    monkeypatch.setattr(client, "search_events", boom)
    r = client.resolve(spec)
    assert not r.ok and "search failed" in r.note


# ---- rundown assembly ----

def _resolved(key, lane, biotech, outcomes, vol=500_000, ok=True):
    return Resolved(key=key, label=key.title(), lane=lane, biotech=biotech, ok=ok,
                    title=key, url="https://polymarket.com/event/x", volume=vol,
                    end_date="2026-12-31", outcomes=outcomes)


def _sample():
    return [
        _resolved("recession", "macro", False, [("Yes", 0.18)]),
        _resolved("rate_cuts", "macro", False, [("0 (0 bps)", 0.77), ("1", 0.14)]),
        _resolved("midterms", "macro", False, [("Democrats Sweep", 0.43), ("R Sen/D House", 0.35)]),
        _resolved("new_pandemic", "healthcare", False, [("Yes", 0.10)]),
        _resolved("rfk_out", "healthcare", False, [("Yes", 0.53)]),
        _resolved("fda_commissioner", "healthcare", False, [("Makary", 0.4)]),
        _resolved("retatrutide", "healthcare", True, [("Yes", 0.12)]),
        _resolved("olezarsen", "healthcare", True, [("Yes", 0.92)], vol=2_200),
    ]


def test_build_lanes_split():
    rd = RD.build(_sample())
    assert {r.key for r in rd.macro} == {"recession", "rate_cuts", "midterms"}
    assert {r.key for r in rd.biotech} == {"retatrutide", "olezarsen"}
    assert {r.key for r in rd.hc_policy} == {"rfk_out", "fda_commissioner"}
    assert {r.key for r in rd.hc_pandemic} == {"new_pandemic"}


def test_aggregated_from_headline_only():
    rd = RD.build(_sample())
    agg = " ".join(rd.aggregated)
    assert "Recession 18%" in agg
    assert "Fed cuts: 0 (0 bps) 77%" in agg
    assert "RFK out 53%" in agg
    assert "Midterms: Democrats Sweep 43%" in agg
    # fda_commissioner is not a headline market
    assert "Makary" not in agg


def _walk(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from _walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from _walk(v)


def test_blocks_satisfy_slack_constraints():
    rd = RD.build(_sample())
    blocks = RD.build_blocks(rd)
    assert blocks[0]["type"] == "header"
    assert len(blocks) <= 50
    for b in blocks:
        if b.get("type") == "context":
            assert "elements" in b and "text" not in b  # the elements[] rule
        if b.get("type") == "section":
            assert len(b["text"]["text"]) <= 3000
        assert b.get("type") != "rich_text"
    for d in _walk(blocks):
        style = d.get("style")
        if isinstance(style, dict):
            assert "underline" not in style


def test_html_has_lanes_and_links():
    rd = RD.build(_sample())
    html = RD.render_html(rd)
    assert "Prediction Markets" in html
    assert "Biotech" in html and "Macro" in html
    assert "polymarket.com/event" in html
    assert "18%" in html


def test_missing_market_renders_gracefully():
    rows = [_resolved("recession", "macro", False, [], ok=False)]
    rows[0].note = "not found"
    rd = RD.build(rows)
    assert "no live market" in RD.render_text(rd)
    # and doesn't crash block/html rendering
    RD.build_blocks(rd)
    RD.render_html(rd)


def test_liquidity_flag_bands():
    assert config.liquidity_flag(300_000) == "🟢"
    assert config.liquidity_flag(50_000) == "🟡"
    assert config.liquidity_flag(2_000) == "🔴"


# ---- history + movers ----

def test_history_record_roundtrip_and_same_day_overwrite(tmp_path):
    p = tmp_path / "h.json"
    now = datetime(2026, 6, 12, tzinfo=_UTC)
    HIST.record([_resolved("recession", "macro", False, [("Yes", 0.18)])], now, path=p)
    assert HIST.load(p)["recession"][-1]["outcomes"] == [["Yes", 0.18]]
    # same UTC day → overwrite, not append
    HIST.record([_resolved("recession", "macro", False, [("Yes", 0.20)])], now, path=p)
    snaps = HIST.load(p)["recession"]
    assert len(snaps) == 1 and snaps[-1]["outcomes"] == [["Yes", 0.20]]


def test_movers_wow_detected_above_threshold():
    now = datetime(2026, 6, 12, tzinfo=_UTC)
    r = _resolved("recession", "macro", False, [("Yes", 0.18)])
    hist = {"recession": [{"date": "2026-06-05", "title": "x", "volume": 1,
                           "outcomes": [["Yes", 0.10]]}]}
    ms = HIST.movers([r], now, hist=hist, threshold_pp=5)
    assert len(ms) == 1 and ms[0].period == "WoW" and round(ms[0].delta_pp) == 8
    # below threshold → nothing
    assert HIST.movers([r], now, hist=hist, threshold_pp=10) == []


def test_movers_yoy_detected():
    now = datetime(2026, 6, 12, tzinfo=_UTC)
    r = _resolved("recession", "macro", False, [("Yes", 0.18)])
    hist = {"recession": [{"date": "2025-06-13", "title": "x", "volume": 1,
                           "outcomes": [["Yes", 0.50]]}]}
    ms = HIST.movers([r], now, hist=hist, threshold_pp=5)
    assert ms and ms[0].period == "YoY" and round(ms[0].delta_pp) == -32


def test_movers_multi_outcome_matches_by_label():
    now = datetime(2026, 6, 12, tzinfo=_UTC)
    r = _resolved("midterms", "macro", False, [("Dems Sweep", 0.44), ("R Sweep", 0.17)])
    hist = {"midterms": [{"date": "2026-06-05", "title": "x", "volume": 1,
                          "outcomes": [["Dems Sweep", 0.30], ["R Sweep", 0.16]]}]}
    ms = HIST.movers([r], now, hist=hist, threshold_pp=5)
    assert len(ms) == 1 and ms[0].outcome == "Dems Sweep" and round(ms[0].delta_pp) == 14


# ---- discovery ----

def test_discovery_seeds_first_run_then_surfaces_new(tmp_path, monkeypatch):
    p = tmp_path / "seen.json"
    monkeypatch.setattr(DISC.client, "search_events",
                        lambda term: [{"title": "FDA approves NewDrug Z?", "slug": "newdrug-z"}])
    # first run seeds silently
    assert DISC.discover_new(datetime(2026, 6, 12, tzinfo=_UTC), path=p) == []
    assert p.exists()
    # a genuinely new, non-tracked, relevant market appears next week
    monkeypatch.setattr(DISC.client, "search_events", lambda term: [
        {"title": "FDA approves NewDrug Z?", "slug": "newdrug-z"},
        {"title": "Avian flu outbreak declared in 2027?", "slug": "avian-2027"},
    ])
    monkeypatch.setattr(DISC.client, "fetch_event", lambda slug: {
        "title": "Avian flu outbreak declared in 2027?", "slug": slug, "closed": False,
        "volume": 50_000, "endDate": "2027-12-31",
        "markets": [{"outcomes": '["Yes","No"]', "outcomePrices": '["0.07","0.93"]'}]})
    out = DISC.discover_new(datetime(2026, 6, 19, tzinfo=_UTC), path=p)
    assert len(out) == 1 and out[0].lane == "healthcare" and out[0].lead_label == "Yes"


def test_discovery_skips_low_volume(tmp_path, monkeypatch):
    p = tmp_path / "seen.json"
    p.write_text("[]", encoding="utf-8")  # not first run
    monkeypatch.setattr(DISC.client, "search_events",
                        lambda term: [{"title": "Recession in Canada in 2027?", "slug": "ca-rec"}])
    monkeypatch.setattr(DISC.client, "fetch_event", lambda slug: {
        "title": "Recession in Canada in 2027?", "slug": slug, "closed": False,
        "volume": 500, "endDate": "2027-12-31",
        "markets": [{"outcomes": '["Yes","No"]', "outcomePrices": '["0.2","0.8"]'}]})
    assert DISC.discover_new(datetime(2026, 6, 19, tzinfo=_UTC), path=p, min_volume=10_000) == []


def test_rundown_renders_movers_and_new_markets():
    now = datetime(2026, 6, 12, tzinfo=_UTC)
    mv = [HIST.Mover("recession", "US recession", "macro", "Yes", 0.10, 0.18, 8.0, "WoW")]
    nm = [DISC.NewMarket("Avian flu outbreak 2027?", "https://polymarket.com/event/x",
                         "healthcare", 50_000, "2027-12-31", "Yes", 0.07)]
    rd = RD.build(_sample(), now, movers=mv, new_markets=nm)
    txt = RD.render_text(rd)
    assert "NOTABLE MOVES" in txt and "NEWLY-OPENED" in txt
    blocks = RD.build_blocks(rd)
    assert len(blocks) <= 50
    for b in blocks:
        if b.get("type") == "section":
            assert len(b["text"]["text"]) <= 3000
    html = RD.render_html(rd)
    assert "Notable moves" in html and "Newly-opened" in html
