"""Run every component and write real metrics to metrics.json (repo root).

Numbers come from actual runs on the local SQLite warehouse -- nothing is
hand-typed. Regenerate any time with:  python -m scripts.collect_metrics
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from peoplepulse.data.source import main as ingest

ROOT = Path(__file__).resolve().parent.parent


def _test_count() -> int:
    """Run the pytest suite and return the number of tests collected.

    Uses a JUnit XML report, which records one <testcase> per test regardless of
    pytest's terminal formatting -- a deterministic count across versions.
    """
    import tempfile
    import xml.etree.ElementTree as ET

    with tempfile.TemporaryDirectory() as td:
        xml = Path(td) / "report.xml"
        subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
             f"--junit-xml={xml}"],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        if not xml.exists():
            return 0
        root = ET.parse(xml).getroot()
        suites = root.findall(".//testsuite") or [root]
        return sum(int(s.get("tests", 0)) for s in suites)


def main() -> dict:
    from eval.run_eval import main as run_eval
    from peoplepulse.mis.build_views import build as build_views
    from peoplepulse.model.train import train
    from peoplepulse.warehouse.load import load

    ingest()
    load_counts = load()
    views = build_views()
    model = train()
    eval_summary = run_eval()

    metrics = {
        "note": (
            "REAL data: IBM HR Analytics Employee Attrition (Kaggle, DbCL-1.0). "
            "All numbers from real runs on the local warehouse."
        ),
        "data": {
            "dataset": "IBM HR Analytics Employee Attrition & Performance (Kaggle)",
            "employees_loaded": load_counts["employees_loaded"],
            "leavers": load_counts["leavers"],
            "rows_quarantined": load_counts["rows_quarantined"],
            "departments": load_counts["departments"],
            "job_roles": load_counts["job_roles"],
        },
        "warehouse": {
            "mis_views": len(views),
            "dimensions": 3,
            "facts": 1,
        },
        "model": {
            "validation": model["validation"],
            "test_size": model["test_size"],
            "overall_attrition_rate": model["overall_attrition_rate"],
            "test_attrition_rate": model["test_attrition_rate"],
            "baseline_f1": model["models"]["baseline_majority"]["f1"],
            "logreg": model["models"]["logistic_regression"],
            "gradient_boosting": model["models"]["gradient_boosting"],
        },
        "genai": {
            "nl2sql_questions": eval_summary["nl2sql_total"],
            "nl2sql_exact_match_accuracy": eval_summary["nl2sql_exact_match_accuracy"],
            "adversarial_prompts": eval_summary["guardrail_total"],
            "guardrail_block_rate": eval_summary["guardrail_block_rate"],
        },
        "tests": {"count": _test_count()},
    }
    out = ROOT / "metrics.json"
    out.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"\nWrote {out}")
    print(json.dumps(metrics, indent=2))
    return metrics


if __name__ == "__main__":
    main()
