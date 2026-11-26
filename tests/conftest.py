"""Shared pytest fixtures.

The `warehouse` fixture builds a full SQLite warehouse once per test session:
generate (deterministic, seed 42) -> load star schema -> build MIS views. It
points DATABASE_URL at a temp DB so tests never touch a real database, while the
raw CSVs are written to the default data_out/raw (what the model reads).
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="session")
def warehouse(tmp_path_factory):
    # In CI, DATABASE_URL points at the Postgres service -> run the whole suite
    # against real Postgres. Locally (unset), use a throwaway SQLite file.
    existing = os.environ.get("DATABASE_URL", "")
    if not existing.startswith("postgresql"):
        db = tmp_path_factory.mktemp("wh") / "test.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"
        os.environ.pop("DATABASE_URL_RO", None)  # RO falls back to the same URL

    from peoplepulse.data.generate import main as generate
    from peoplepulse.mis.build_views import build as build_views
    from peoplepulse.warehouse.load import load

    generate()  # writes data_out/raw (default location the model reads)
    load()  # loads into the target DB (SQLite locally, Postgres in CI)
    build_views()
    return {"url": os.environ["DATABASE_URL"]}
