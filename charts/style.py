"""Shared matplotlib styling — kept tight so all charts look consistent."""

import matplotlib.pyplot as plt
from matplotlib import rcParams

# Slack renders best with a 16:9 or 4:3 PNG at reasonable DPI.
DEFAULT_FIGSIZE = (11, 6)
DEFAULT_DPI = 110

# Color cycle: headline first, then secondary, then accents.
COLOR_PRIMARY = "#1F4E79"   # deep blue (headline)
COLOR_SECONDARY = "#C00000" # red (core / secondary)
COLOR_ACCENT_1 = "#548235"  # green
COLOR_ACCENT_2 = "#BF8F00"  # gold
COLOR_ACCENT_3 = "#7030A0"  # purple
COLOR_REFERENCE = "#666666" # gray (target lines, etc.)
COLOR_GRID = "#E0E0E0"

CYCLE = [COLOR_PRIMARY, COLOR_SECONDARY, COLOR_ACCENT_1, COLOR_ACCENT_2, COLOR_ACCENT_3]


def apply_default_style() -> None:
    """Apply chart-wide defaults. Call once at module import or in the
    chart factory before plotting.
    """
    rcParams["font.family"] = "DejaVu Sans"  # bundled with matplotlib
    rcParams["font.size"] = 11
    rcParams["axes.titlesize"] = 13
    rcParams["axes.titleweight"] = "bold"
    rcParams["axes.labelsize"] = 11
    rcParams["axes.edgecolor"] = "#333333"
    rcParams["axes.linewidth"] = 1.0
    rcParams["axes.grid"] = True
    rcParams["axes.grid.axis"] = "y"
    rcParams["grid.color"] = COLOR_GRID
    rcParams["grid.linewidth"] = 0.8
    rcParams["legend.frameon"] = False
    rcParams["legend.fontsize"] = 10
    rcParams["xtick.labelsize"] = 10
    rcParams["ytick.labelsize"] = 10
    rcParams["figure.dpi"] = DEFAULT_DPI


# Auto-apply on import. matplotlib state is global anyway.
apply_default_style()
