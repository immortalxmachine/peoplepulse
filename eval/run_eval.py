"""Evaluate the GenAI HR query assistant.

Two measures, both from real runs (mock provider, so fully reproducible):

  1. Exact-match accuracy on 25 hand-written questions. For each question we run
     the full pipeline (translate -> guardrail -> execute) and compare its result
     to a hand-written REFERENCE query's result (rounded). A match means the
     assistant routed to the right view AND applied the right filters.

  2. Guardrail block-rate on 10 adversarial prompts (PII requests, SQL injection,
     write attempts, off-topic). Every one must be refused.

Run:  python -m eval.run_eval
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import create_engine, text

from peoplepulse.api.nl2sql import answer
from peoplepulse.config import DATA_OUT, database_url

HERE = Path(__file__).parent


def _round_cell(v: object) -> object:
    if isinstance(v, bool):
        return v
    if isinstance(v, float):
        return round(v, 2)
    if isinstance(v, int):
        return v
    return str(v)


def _norm(rows: list[list]) -> list[tuple]:
    return sorted(tuple(_round_cell(c) for c in row) for row in rows)


def run_accuracy() -> dict:
    questions = json.loads((HERE / "questions.json").read_text(encoding="utf-8"))
    engine = create_engine(database_url())
    passed, details = 0, []
    with engine.connect() as conn:
        for item in questions:
            q, ref_sql = item["question"], item["reference_sql"]
            expected = _norm([list(r) for r in conn.execute(text(ref_sql)).fetchall()])
            res = answer(q)
            actual = _norm(res.rows) if (not res.refused and res.rows is not None) else None
            ok = actual is not None and actual == expected
            passed += int(ok)
            details.append({"question": q, "pass": ok, "expected": expected, "actual": actual})
    return {
        "total": len(questions),
        "passed": passed,
        "accuracy": round(passed / len(questions), 4),
        "details": details,
    }


def run_guardrails() -> dict:
    prompts = json.loads((HERE / "adversarial.json").read_text(encoding="utf-8"))
    blocked, details = 0, []
    for p in prompts:
        res = answer(p)
        blocked += int(res.refused)
        details.append({"prompt": p, "refused": res.refused, "reason": res.reason})
    return {
        "total": len(prompts),
        "blocked": blocked,
        "block_rate": round(blocked / len(prompts), 4),
        "details": details,
    }


def main() -> dict:
    acc = run_accuracy()
    guard = run_guardrails()
    summary = {
        "nl2sql_exact_match_accuracy": acc["accuracy"],
        "nl2sql_passed": acc["passed"],
        "nl2sql_total": acc["total"],
        "guardrail_block_rate": guard["block_rate"],
        "guardrail_blocked": guard["blocked"],
        "guardrail_total": guard["total"],
    }
    out = DATA_OUT / "eval_metrics.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"summary": summary, "accuracy": acc, "guardrails": guard}, indent=2),
        encoding="utf-8",
    )

    print("GenAI HR assistant evaluation (mock provider):")
    print(f"  NL->SQL exact-match accuracy : {acc['passed']}/{acc['total']} "
          f"= {acc['accuracy']:.0%}")
    if acc["passed"] < acc["total"]:
        for d in acc["details"]:
            if not d["pass"]:
                print(f"    MISS: {d['question']}")
                print(f"          expected={d['expected']} actual={d['actual']}")
    print(f"  Guardrail block-rate         : {guard['blocked']}/{guard['total']} "
          f"= {guard['block_rate']:.0%}")
    print(f"  -> {out}")
    return summary


if __name__ == "__main__":
    main()
