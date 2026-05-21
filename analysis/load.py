"""CSV loading and variant lookup.

Per spec FR-001 (as scoped by Clarifications session 2026-05-21), only two
CSVs are loaded: `ots_chat.csv` and `redirects.csv`. `actions.csv` and
`ots_matched_hotels.csv` are intentionally skipped.

Variant labels come from `ots_chat.csv` only. If the same `utid` appears with
both `A` and `B` labels within `ots_chat.csv`, those rows are dropped from
comparative analysis (per FR-003 scoped to in-file consistency).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

OTS_CHAT_FILE = "ots_chat.csv"
REDIRECTS_FILE = "redirects.csv"

OTS_CHAT_DTYPES: dict[str, str] = {
    "utid": "string",
    "chat_session_id": "string",
    "chat_type": "category",
    "rounds": "Int32",
    "request_id": "string",
    "correlation_id": "string",
    "variant": "category",
}

REDIRECTS_DTYPES: dict[str, str] = {
    "utid": "string",
    "pre_redirect_id": "string",
}


@dataclass(frozen=True)
class DataBundle:
    """In-memory container for the two loaded CSVs."""

    ots_chat: pd.DataFrame
    redirects: pd.DataFrame
    data_dir: Path


def load_data(data_dir: str | Path) -> DataBundle:
    """Load `ots_chat.csv` and `redirects.csv` from `data_dir`.

    Raises FileNotFoundError with a one-line diagnosis if either file is
    missing. The CLI maps this to exit code 2.
    """
    data_dir = Path(data_dir)
    ots_chat_path = data_dir / OTS_CHAT_FILE
    redirects_path = data_dir / REDIRECTS_FILE

    if not ots_chat_path.is_file():
        raise FileNotFoundError(f"Required input missing: {ots_chat_path}")
    if not redirects_path.is_file():
        raise FileNotFoundError(f"Required input missing: {redirects_path}")

    ots_chat = pd.read_csv(
        ots_chat_path,
        dtype=OTS_CHAT_DTYPES,
        parse_dates=["dt"],
    )
    redirects = pd.read_csv(
        redirects_path,
        dtype=REDIRECTS_DTYPES,
        parse_dates=["dt"],
    )

    return DataBundle(ots_chat=ots_chat, redirects=redirects, data_dir=data_dir)


def build_variant_lookup(ots_chat: pd.DataFrame) -> tuple[pd.Series, set[str]]:
    """Build `utid -> variant` from `ots_chat`.

    Returns (variant_lookup, excluded_utids) where excluded_utids is the set
    of utids that appear with both `A` and `B` within `ots_chat.csv` (in-file
    conflict). Conflicting utids are excluded from the lookup.
    """
    pairs = ots_chat[["utid", "variant"]].drop_duplicates()
    variant_counts = pairs.groupby("utid", observed=True)["variant"].nunique()
    excluded = set(variant_counts[variant_counts > 1].index.astype(str))

    clean = pairs[~pairs["utid"].isin(excluded)]
    lookup = clean.set_index("utid")["variant"].astype("string")
    return lookup, excluded


def compute_variant_population(
    ots_chat: pd.DataFrame, excluded_utids: set[str]
) -> dict[str, int]:
    """Return the count of distinct utids per variant in `ots_chat`.

    The denominator for FR-013 funnel rates: users who had at least one
    chat event of either type (SUGGESTIONS or INTENT_RECOGNITION).
    """
    clean = ots_chat[~ots_chat["utid"].isin(excluded_utids)]
    counts = (
        clean.drop_duplicates(["utid", "variant"])
        .groupby("variant", observed=True)["utid"]
        .nunique()
    )
    return {str(v): int(counts.get(v, 0)) for v in ("A", "B")}
