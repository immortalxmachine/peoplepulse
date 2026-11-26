"""Run the whole warehouse pipeline end to end.

  generate raw CSVs -> load star schema (+ DQ) -> build MIS views

Idempotent: safe to re-run. This is what CI and `make all` call before training
the model, serving the API, or launching the dashboard.

Run:  python -m peoplepulse.pipeline
"""

from __future__ import annotations

from peoplepulse.data.generate import main as generate
from peoplepulse.mis.build_views import build as build_views
from peoplepulse.warehouse.load import load


def run() -> dict:
    gen = generate()
    load_counts = load()
    views = build_views()
    return {
        "generated": gen,
        "loaded": load_counts,
        "views_built": len(views),
    }


if __name__ == "__main__":
    run()
    print("\nPipeline complete. Next: python -m peoplepulse.model.train / eval.run_eval")
