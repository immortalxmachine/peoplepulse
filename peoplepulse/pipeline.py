"""Run the whole warehouse pipeline end to end.

  ingest real CSV -> load star schema (+ DQ) -> build MIS views

Idempotent: safe to re-run. This is what CI and `make all` call before training
the model, serving the API, or launching the dashboard.

Run:  python -m peoplepulse.pipeline
"""

from __future__ import annotations

from peoplepulse.data.source import main as ingest
from peoplepulse.mis.build_views import build as build_views
from peoplepulse.warehouse.load import load


def run() -> dict:
    ingested = ingest()
    load_counts = load()
    views = build_views()
    return {
        "ingested": ingested,
        "loaded": load_counts,
        "views_built": len(views),
    }


if __name__ == "__main__":
    run()
    print("\nPipeline complete. Next: python -m peoplepulse.model.train / eval.run_eval")
