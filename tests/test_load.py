"""Tests for analysis.load."""

from __future__ import annotations

from pathlib import Path

import pytest

from analysis.load import (
    build_variant_lookup,
    compute_variant_population,
    load_data,
)


def test_load_reads_both_csvs(fixtures_dir: Path) -> None:
    bundle = load_data(fixtures_dir)
    assert bundle.ots_chat.shape[0] == 10  # 10 rows in tiny_ots_chat.csv
    assert bundle.redirects.shape[0] == 4
    assert set(bundle.ots_chat["chat_type"].unique()) == {
        "CHAT_TYPE_SUGGESTIONS",
        "CHAT_TYPE_INTENT_RECOGNITION",
    }


def test_load_raises_on_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_data(tmp_path)


def test_variant_lookup_drops_in_file_conflicts(fixtures_dir: Path) -> None:
    bundle = load_data(fixtures_dir)
    lookup, excluded = build_variant_lookup(bundle.ots_chat)
    # Tiny fixture has no in-file variant conflicts inside ots_chat.csv.
    assert excluded == set()
    assert set(lookup.unique()) <= {"A", "B"}
    assert lookup.loc["u1"] == "A"
    assert lookup.loc["u3"] == "B"


def test_variant_population_matches_distinct_session_ids(fixtures_dir: Path) -> None:
    bundle = load_data(fixtures_dir)
    _, excluded = build_variant_lookup(bundle.ots_chat)
    pop = compute_variant_population(bundle.ots_chat, excluded)
    # Hand-counted from tiny_ots_chat.csv: A = {u1, u2}; B = {u3, u4, u5, u6}.
    # u5 has variant=B in the chat fixture (no in-file conflict because all
    # u5 rows in the fixture have variant=B). After dropping the actions.csv
    # cross-check, u5 stays in the B population.
    assert pop == {"A": 2, "B": 4}
