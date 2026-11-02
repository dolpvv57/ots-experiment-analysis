"""CSV loading and variant lookup.

Primary CSVs are `ots_chat.csv` and `redirects.csv`. `actions.csv` is loaded
optionally (present → included in row counts and frontend variant population;
absent → skipped silently).

Variant labels come from `ots_chat.csv` only. If the same `session_id` appears with
both `A` and `B` labels within `ots_chat.csv`, those rows are dropped from
comparative analysis.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

OTS_CHAT_FILE = "ots_chat.csv"
REDIRECTS_FILE = "redirects.csv"
ACTIONS_FILE = "actions.csv"

OTS_CHAT_DTYPES: dict[str, str] = {
    "session_id": "string",
    "chat_session_id": "string",
    "chat_type": "category",
    "rounds": "Int32",
    "request_id": "string",
    "correlation_id": "string",
    "variant": "category",
}

REDIRECTS_DTYPES: dict[str, str] = {
    "session_id": "string",
    "pre_redirect_id": "string",
}

ACTIONS_DTYPES: dict[str, str] = {
    "session_id": "string",
    "variant": "category",
}


@dataclass(frozen=True)
class DataBundle:
    """In-memory container for loaded CSVs. `actions` is None if the file is absent."""

    ots_chat: pd.DataFrame
    redirects: pd.DataFrame
    data_dir: Path
    actions: pd.DataFrame | None = None


def load_data(data_dir: str | Path) -> DataBundle:
    """Load CSVs from `data_dir`. `actions.csv` is optional; absent -> None.

    Raises FileNotFoundError if `ots_chat.csv` or `redirects.csv` is missing.
    """
    data_dir = Path(data_dir)
    ots_chat_path = data_dir / OTS_CHAT_FILE
    redirects_path = data_dir / REDIRECTS_FILE
    actions_path = data_dir / ACTIONS_FILE

    if not ots_chat_path.is_file():
        raise FileNotFoundError(f"Required input missing: {ots_chat_path}")
    if not redirects_path.is_file():
        raise FileNotFoundError(f"Required input missing: {redirects_path}")

    ots_chat = pd.read_csv(ots_chat_path, dtype=OTS_CHAT_DTYPES, parse_dates=["dt"])
    redirects = pd.read_csv(redirects_path, dtype=REDIRECTS_DTYPES, parse_dates=["dt"])
    actions = (
        pd.read_csv(actions_path, dtype=ACTIONS_DTYPES, parse_dates=["dt"])
        if actions_path.is_file()
        else None
    )

    return DataBundle(ots_chat=ots_chat, redirects=redirects, data_dir=data_dir, actions=actions)


def build_variant_lookup(ots_chat: pd.DataFrame) -> tuple[pd.Series, set[str]]:
    """Build `session_id -> variant` from `ots_chat`.

    Returns (variant_lookup, excluded_session_ids) where excluded_session_ids is the set
    of session_ids that appear with both `A` and `B` within `ots_chat.csv` (in-file
    conflict). Conflicting session_ids are excluded from the lookup.
    """
    pairs = ots_chat[["session_id", "variant"]].drop_duplicates()
    variant_counts = pairs.groupby("session_id", observed=True)["variant"].nunique()
    excluded = set(variant_counts[variant_counts > 1].index.astype(str))

    clean = pairs[~pairs["session_id"].isin(excluded)]
    lookup = clean.set_index("session_id")["variant"].astype("string")
    return lookup, excluded


def compute_variant_population(
    ots_chat: pd.DataFrame, excluded_session_ids: set[str]
) -> dict[str, int]:
    """Return the count of distinct session_ids per variant in `ots_chat`.

    The denominator for FR-013 funnel rates: users who had at least one
    chat event of either type (SUGGESTIONS or INTENT_RECOGNITION).
    """
    clean = ots_chat[~ots_chat["session_id"].isin(excluded_session_ids)]
    counts = (
        clean.drop_duplicates(["session_id", "variant"])
        .groupby("variant", observed=True)["session_id"]
        .nunique()
    )
    return {str(v): int(counts.get(v, 0)) for v in ("A", "B")}
