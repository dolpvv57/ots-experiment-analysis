"""Plugin interface contract and shared container for experiment-specific sections.

Each experiment directory may contain a ``plugin.py`` that the framework
discovers automatically.  The framework calls duck-typed functions — no
inheritance required.  Every ``plugin.py`` must expose:

    TEMPLATE_FRAGMENT: str
        Path to the Jinja2 section template, relative to the plugin file's
        directory (e.g. ``"templates/section.html.j2"``).

    def compute(bundle: DataBundle, excluded_utids: set[str]) -> Any
        Run the experiment-specific analysis and return a section dataclass.
        Use ``bundle.data_dir`` to load extra CSV files (e.g. actions.csv).

    def count_tests(section: Any) -> int
        Return how many statistical hypothesis tests the section contributes
        (used for the total-tests / expected-false-positives annotation).

Optional:

    def build_charts(section: Any) -> dict[str, str]
        Return a mapping of chart_id -> Plotly HTML div string.
        Omit entirely if the section has no charts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PluginSection:
    """Container produced by the framework after running a plugin."""

    section: Any
    template_path: Path
    charts: dict[str, str] = field(default_factory=dict)
    test_count: int = 0
