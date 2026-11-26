"""End-to-end checks for the eval harness and the attrition model."""

from __future__ import annotations

from eval.run_eval import run_accuracy, run_guardrails
from peoplepulse.model.train import train


def test_nl2sql_eval_accuracy(warehouse):
    acc = run_accuracy()
    # The rule-based mock is designed to answer all 15; allow a small margin.
    assert acc["accuracy"] >= 0.9


def test_guardrail_block_rate(warehouse):
    guard = run_guardrails()
    assert guard["block_rate"] == 1.0  # every adversarial prompt must be refused


def test_model_beats_baseline(warehouse):
    res = train()
    logreg = res["models"]["logistic_regression"]
    baseline = res["models"]["baseline_majority"]
    # The model must find real signal: better F1 than the majority baseline and
    # an ROC-AUC above chance.
    assert logreg["f1"] > baseline["f1"]
    assert logreg["roc_auc"] > 0.55
    assert res["test_rows"] > 0
