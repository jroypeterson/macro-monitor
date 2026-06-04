"""Macro data inventory — a standing catalog of macro datasets we encounter.

Source of truth is ``datasets.yaml`` (one entry per dataset); ``SCHEMA.md`` defines the
fields. Render a human-readable table with ``python -m macro_monitor.data_inventory.render``
(or ``python -m macro_monitor.cli inventory``).

Seeded 2026-06-03 from the "Ahead of the Curve" (Joseph Ellis) chart-recreation work —
the ~18 series the book uses, mapped to their FRED ids. Grow it whenever a new macro
dataset is encountered, used or not.
"""
