"""Attrition model: predict whether an employee has left (IBM HR dataset).

The source is cross-sectional — one row per employee with a known ``Attrition``
outcome — so this is a standard supervised classification problem, not an
out-of-time forecast (there are no hire/exit dates to split on). We therefore
use a **stratified train/test split** (75/25, fixed seed), which preserves the
~16% attrition base rate in both folds. This is the canonical way this public
dataset is modelled.

Features are the employee's attributes and measures as stored in the warehouse
(nothing derived from the label). "Attrition = Yes" is the positive class; recall
on it is what an HR team cares about (a missed flight-risk is the costly error).

Models compared on the held-out test fold:
  * majority-class baseline (always predict "stays")
  * logistic regression (scaled + one-hot, class_weight balanced)
  * histogram gradient boosting (balanced sample weights)

Metrics: precision / recall / F1 / ROC-AUC, plus feature importance.

Run:  python -m peoplepulse.model.train
"""

from __future__ import annotations

import json

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sqlalchemy import create_engine, text

from peoplepulse.config import DATA_OUT, database_url

RANDOM_STATE = 42
TEST_SIZE = 0.25

CATEGORICAL = [
    "department_name", "job_role", "gender", "marital_status",
    "business_travel", "overtime", "education_field",
]
NUMERIC = [
    "age", "monthly_income", "distance_from_home", "total_working_years",
    "years_at_company", "years_in_current_role", "years_since_last_promotion",
    "years_with_curr_manager", "num_companies_worked", "percent_salary_hike",
    "training_times_last_year", "job_level", "job_satisfaction",
    "environment_satisfaction", "job_involvement", "relationship_satisfaction",
    "work_life_balance", "stock_option_level",
]


def _load_dataset() -> pd.DataFrame:
    """One row per employee: features from the star schema + attrition label."""
    engine = create_engine(database_url())
    sql = """
        SELECT e.gender, e.age, e.marital_status, e.business_travel, e.overtime,
               e.job_level, e.education_field, e.attrition,
               dep.department_name, r.job_role,
               f.monthly_income, f.distance_from_home, f.total_working_years,
               f.years_at_company, f.years_in_current_role,
               f.years_since_last_promotion, f.years_with_curr_manager,
               f.num_companies_worked, f.percent_salary_hike,
               f.training_times_last_year, f.job_satisfaction,
               f.environment_satisfaction, f.job_involvement,
               f.relationship_satisfaction, f.work_life_balance,
               f.stock_option_level
        FROM dim_employee e
        JOIN dim_department dep ON dep.department_key = e.department_key
        JOIN dim_job_role   r   ON r.job_role_key     = e.job_role_key
        JOIN fact_employee  f   ON f.employee_key      = e.employee_key
    """
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn)


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
                    max_iter=2000, class_weight="balanced", random_state=RANDOM_STATE
                ),
            ),
        ]
    )
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
    """Train + evaluate all models on a stratified hold-out. Returns metrics."""
    data = _load_dataset()
    feats = CATEGORICAL + NUMERIC
    x, y = data[feats], data["attrition"].astype(int)

    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=TEST_SIZE, stratify=y, random_state=RANDOM_STATE
    )

    results: dict = {
        "dataset": "IBM HR Analytics Employee Attrition (Kaggle, DbCL-1.0)",
        "validation": "stratified hold-out",
        "test_size": TEST_SIZE,
        "n_employees": int(len(data)),
        "train_rows": int(len(x_train)),
        "test_rows": int(len(x_test)),
        "overall_attrition_rate": round(float(y.mean()), 4),
        "test_attrition_rate": round(float(y_test.mean()), 4),
        "models": {},
    }

    base = DummyClassifier(strategy="most_frequent")
    base.fit(x_train, y_train)
    results["models"]["baseline_majority"] = _scores(y_test, base.predict(x_test), None)

    pipelines = _make_pipelines()
    for name, pipe in pipelines.items():
        if name == "gradient_boosting":
            w = y_train.map(
                {0: 1.0, 1: float((y_train == 0).sum() / max((y_train == 1).sum(), 1))}
            )
            pipe.fit(x_train, y_train, clf__sample_weight=w.values)
        else:
            pipe.fit(x_train, y_train)
        proba = pipe.predict_proba(x_test)[:, 1]
        pred = (proba >= 0.5).astype(int)
        results["models"][name] = _scores(y_test, pred, proba)

    # Logistic-regression coefficients (signed drivers).
    logreg = pipelines["logistic_regression"]
    ohe_names = list(
        logreg.named_steps["pre"].named_transformers_["cat"].get_feature_names_out(CATEGORICAL)
    )
    coef_names = ohe_names + NUMERIC
    coefs = logreg.named_steps["clf"].coef_[0]
    top = sorted(zip(coef_names, coefs, strict=True), key=lambda t: abs(t[1]), reverse=True)[:10]
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
    )[:10]
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
        f"Attrition model (stratified hold-out, test_size={res['test_size']}) "
        f"on {res['n_employees']} real employees"
    )
    print(
        f"  train rows {res['train_rows']} | test rows {res['test_rows']} "
        f"(attrition {res['test_attrition_rate']:.1%})"
    )
    print(f"  {'model':22s} {'prec':>6s} {'rec':>6s} {'f1':>6s} {'auc':>6s}")
    for name, m in res["models"].items():
        auc = f"{m['roc_auc']:.3f}" if m["roc_auc"] is not None else "   -  "
        print(f"  {name:22s} {m['precision']:6.3f} {m['recall']:6.3f} {m['f1']:6.3f} {auc:>6s}")
    print(f"  -> {out}")
    return res


if __name__ == "__main__":
    main()
