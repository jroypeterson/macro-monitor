# macro_monitor — Project Instructions

See `README.md` for the full project description, workflows, and secrets table.

- **[ClaudeFin] email alerts** (root `CONVENTIONS.md` §5 "Email alerts"): the weekly Ahead-of-the-Curve rebuild lane (`ahead_of_curve.yml`, Mon 11:00 UTC → `cli ahead-of-curve --email`) emails a short pointer alert via the self-contained `email_alert_client.py` (vendored, not the `_shared/` shim, because this lane runs in CI). Subject grammar `[ClaudeFin] macro_monitor — <what>` (pass only the `<what>` part); **non-gating** — a failed send is a stderr `[WARN]` + Actions `::warning::`, never a failed run; **weekly-lane-only** — do NOT add email alerts to daily lanes (releases, fed-speeches, research digest).
