"""Attrition-risk model: predict whether an active employee leaves within 12 months.

Why an *out-of-time* (time-based) split rather than a random one
---------------------------------------------------------------
Attrition is a forecasting problem: in production you train on the past and
score today's employees for the future. A random train/test shuffle would let
the model peek at the same time period it is evaluated on. So we build two
"as-of" snapshots a year apart with non-overlapping forward label windows:

  TRAIN  cutoff 2023-12-31  ->  label = left during 2024
  TEST   cutoff 2024-12-31  ->  label = left during 2025

Population at each cutoff = employees active on that date (hired on/before it and
not yet exited). Features are only things knowable *as of* the cutoff. An
employee active at both cutoffs can appear in both folds -- that mirrors real
out-of-time validation and the two label windows never overlap.

Models compared (on the TEST snapshot):
  * majority-class baseline (always predict "stays")
  * logistic regression (scaled + one-hot, class_weight balanced)
  * histogram gradient boosting (balanced sample weights)

Metrics: precision / recall / F1 / ROC-AUC, plus feature importance.

Run:  python -m peoplepulse.model.train
"""

from __future__ import annotations

import datetime as dt
import json

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sqlalchemy import create_engine, text

from peoplepulse.config import DATA_OUT, database_url
from peoplepulse.data.generate import BAND_BY_GRADE, GRADES

RANDOM_STATE = 42

TRAIN_CUTOFF = dt.date(2023, 12, 31)
TEST_CUTOFF = dt.date(2024, 12, 31)
LABEL_MONTHS = 12

CATEGORICAL = ["department_name", "country_name", "gender"]
NUMERIC = ["tenure_days", "grade_ordinal", "annual_ctc_usd", "comp_ratio", "rating_asof"]

# Grade -> band midpoint (for the comp_ratio feature).
_BAND_MID = {g: (lo + hi) / 2 for g, (_code, lo, hi) in BAND_BY_GRADE.items()}
_GRADE_ORD = {g: i + 1 for i, g in enumerate(GRADES)}


def _add_months(d: dt.date, months: int) -> dt.date:
    """Date `months` after d (clamped to end of month)."""
    import calendar

    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    day = min(d.day, calendar.monthrange(y, m)[1])
    return dt.date(y, m, day)


def _load_employees() -> pd.DataFrame:
    """Employees with dimension names + parsed dates and a rating history."""
    engine = create_engine(database_url())
    sql = """
        SELECT e.employee_id, e.gender, e.grade, e.band, e.annual_ctc_usd,
               e.hire_date, e.exit_date,
               dep.department_name, co.country_name
        FROM dim_employee e
        JOIN dim_department dep ON dep.department_key = e.department_key
        JOIN dim_country co     ON co.country_key = e.country_key
    """
    with engine.connect() as conn:
        emp = pd.read_sql(text(sql), conn)
    # Convert to python date / None (not NaT) so date comparisons are clean.
    emp["hire_date"] = pd.to_datetime(emp["hire_date"]).apply(
        lambda t: t.date() if pd.notna(t) else None
    )
    emp["exit_date"] = pd.to_datetime(emp["exit_date"]).apply(
        lambda t: t.date() if pd.notna(t) else None
    )
    # Performance history (as-of rating lookups).
    perf = pd.read_csv(DATA_OUT / "raw" / "raw_performance.csv")
    return emp, perf


def _rating_asof(perf: pd.DataFrame, employee_id: str, year: int) -> float:
    """Most recent rating in a review year <= `year`, else NaN."""
    hist = perf[(perf["employee_id"] == employee_id) & (perf["review_year"] <= year)]
    if hist.empty:
        return np.nan
    return float(hist.loc[hist["review_year"].idxmax(), "rating"])


def build_snapshot(emp: pd.DataFrame, perf: pd.DataFrame, cutoff: dt.date) -> pd.DataFrame:
    """One row per employee active at `cutoff`, with as-of features + label."""
    label_end = _add_months(cutoff, LABEL_MONTHS)
    # Active at cutoff = hired on/before cutoff and not exited on/before cutoff.
    hired = emp["hire_date"].apply(lambda h: h is not None and h <= cutoff)
    not_left = emp["exit_date"].apply(lambda ed: ed is None or ed > cutoff)
    active = emp[hired & not_left].copy()

    active["tenure_days"] = active["hire_date"].apply(lambda h: (cutoff - h).days)
    active["grade_ordinal"] = active["grade"].map(_GRADE_ORD)
    active["comp_ratio"] = active.apply(
        lambda r: r["annual_ctc_usd"] / _BAND_MID[r["grade"]], axis=1
    )
    active["rating_asof"] = active["employee_id"].apply(
        lambda eid: _rating_asof(perf, eid, cutoff.year)
    )
    # Label: exits within (cutoff, cutoff + LABEL_MONTHS].
    active["label"] = active["exit_date"].apply(
        lambda ed: 1 if (ed is not None and cutoff < ed <= label_end) else 0
    )
    return active


def _make_pipelines() -> dict[str, Pipeline]:
    pre = ColumnTransformer(
        [
            ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
            ("num", StandardScaler(), NUMERIC),
        ]
    )
    logreg = Pipeline(
        [
            ("pre", pre),
            (
                "clf",
                LogisticRegression(
                    max_iter=1000, class_weight="balanced", random_state=RANDOM_STATE
                ),
            ),
        ]
    )
    # Gradient boosting handles raw numerics; still one-hot the categoricals.
    gbm = Pipeline(
        [
            ("pre", pre),
            (
                "clf",
                HistGradientBoostingClassifier(
                    max_depth=3, learning_rate=0.1, random_state=RANDOM_STATE
                ),
            ),
        ]
    )
    return {"logistic_regression": logreg, "gradient_boosting": gbm}


def _scores(y_true, y_pred, y_proba) -> dict[str, float]:
    return {
        "precision": round(precision_score(y_true, y_pred, zero_division=0), 4),
        "recall": round(recall_score(y_true, y_pred, zero_division=0), 4),
        "f1": round(f1_score(y_true, y_pred, zero_division=0), 4),
        "roc_auc": round(roc_auc_score(y_true, y_proba), 4) if y_proba is not None else None,
    }


def train() -> dict:
    """Train + evaluate all models out-of-time. Returns a metrics dict."""
    emp, perf = _load_employees()
    train_df = build_snapshot(emp, perf, TRAIN_CUTOFF)
    test_df = build_snapshot(emp, perf, TEST_CUTOFF)

    feats = CATEGORICAL + NUMERIC
    x_train, y_train = train_df[feats], train_df["label"]
    x_test, y_test = test_df[feats], test_df["label"]

    results: dict = {
        "train_cutoff": TRAIN_CUTOFF.isoformat(),
        "test_cutoff": TEST_CUTOFF.isoformat(),
        "label_horizon_months": LABEL_MONTHS,
        "train_rows": int(len(train_df)),
        "test_rows": int(len(test_df)),
        "train_attrition_rate": round(float(y_train.mean()), 4),
        "test_attrition_rate": round(float(y_test.mean()), 4),
        "models": {},
    }

    # Baseline: majority class.
    base = DummyClassifier(strategy="most_frequent")
    base.fit(x_train, y_train)
    results["models"]["baseline_majority"] = _scores(
        y_test, base.predict(x_test), None
    )

    pipelines = _make_pipelines()
    for name, pipe in pipelines.items():
        if name == "gradient_boosting":
            # Balanced sample weights so the minority (leavers) is not ignored.
            w = y_train.map({0: 1.0, 1: float((y_train == 0).sum() / max((y_train == 1).sum(), 1))})
            pipe.fit(x_train, y_train, clf__sample_weight=w.values)
        else:
            pipe.fit(x_train, y_train)
        proba = pipe.predict_proba(x_test)[:, 1]
        pred = (proba >= 0.5).astype(int)
        results["models"][name] = _scores(y_test, pred, proba)

    # Feature importance from logistic-regression coefficients.
    logreg = pipelines["logistic_regression"]
    ohe_names = list(
        logreg.named_steps["pre"].named_transformers_["cat"].get_feature_names_out(CATEGORICAL)
    )
    coef_names = ohe_names + NUMERIC
    coefs = logreg.named_steps["clf"].coef_[0]
    top = sorted(zip(coef_names, coefs, strict=True), key=lambda t: abs(t[1]), reverse=True)[:8]
    results["logreg_top_features"] = [
        {"feature": n, "coef": round(float(c), 4)} for n, c in top
    ]

    # Permutation importance for the gradient-boosting model (model-agnostic).
    gbm = pipelines["gradient_boosting"]
    perm = permutation_importance(
        gbm, x_test, y_test, scoring="roc_auc", n_repeats=5, random_state=RANDOM_STATE
    )
    perm_rank = sorted(
        zip(feats, perm.importances_mean, strict=True), key=lambda t: t[1], reverse=True
    )[:8]
    results["gbm_permutation_importance"] = [
        {"feature": n, "importance": round(float(v), 4)} for n, v in perm_rank
    ]
    return results


def main() -> dict:
    res = train()
    out = DATA_OUT / "model_metrics.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2), encoding="utf-8")

    print(
        f"Out-of-time attrition model  "
        f"(train {res['train_cutoff']} -> test {res['test_cutoff']})"
    )
    print(
        f"  train rows {res['train_rows']} (attrition {res['train_attrition_rate']:.1%}) | "
        f"test rows {res['test_rows']} (attrition {res['test_attrition_rate']:.1%})"
    )
    print(f"  {'model':22s} {'prec':>6s} {'rec':>6s} {'f1':>6s} {'auc':>6s}")
    for name, m in res["models"].items():
        auc = f"{m['roc_auc']:.3f}" if m["roc_auc"] is not None else "   -  "
        print(f"  {name:22s} {m['precision']:6.3f} {m['recall']:6.3f} {m['f1']:6.3f} {auc:>6s}")
    print(f"  -> {out}")
    return res


if __name__ == "__main__":
    main()
