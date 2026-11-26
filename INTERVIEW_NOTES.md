# PeoplePulse — Interview Notes

20 questions and answers tied to specific files/functions. Data is the **real,
public** IBM HR Analytics Employee Attrition dataset (Kaggle, DbCL-1.0).

### 1. What is PeoplePulse in one sentence?
A people-analytics MIS over the real IBM HR Attrition dataset, with a guard-railed
GenAI natural-language-to-SQL assistant, an attrition-risk model, and a low-code
onboarding workflow — covering analytics, dashboards, GenAI, low-code, and
governance.

### 2. Where does the data come from, and why this dataset?
The **IBM HR Analytics Employee Attrition & Performance** dataset on Kaggle
(`pavansubhasht/ibm-hr-analytics-attrition-dataset`, License DbCL-1.0): 1,470
employees of a *fictional* company, published by IBM as a public teaching set. It
has a real `Attrition` outcome with no real individual's data (so no PII risk),
and `peoplepulse/data/source.py` only projects/renames its columns — it fabricates
nothing.

### 3. It's cross-sectional — what does that constrain?
It's a single snapshot (one row per employee, no hire/exit dates, one company).
So PeoplePulse models cross-sectional attrition and a prediction model, and does
**not** fake time-series headcount, a hiring funnel, time-to-hire, or multiple
countries. There is no public HRIS dataset with real dated events — that's PII —
so inventing those would mean going back to synthetic, which the project avoids.

### 4. Walk me through the warehouse schema.
A Kimball star in `peoplepulse/warehouse/schema.py`: `dim_department`,
`dim_job_role`, `dim_education`, a `dim_employee` hub (descriptive attributes +
the attrition label), the `fact_employee` fact (numeric measures per employee),
and a `quarantine` table. Surrogate keys are assigned in Python so DDL and inserts
are identical on SQLite and Postgres.

### 5. What data-quality checks run, and what happens to bad rows?
`peoplepulse/warehouse/quality.py` checks null IDs, duplicate IDs, an invalid
`Attrition` label, unknown departments, out-of-range survey/level ordinals, and
negative measures. Bad rows are **not dropped** — they go to the `quarantine`
table with a reason. The published dataset is clean, so **0 rows are quarantined**;
`tests/test_quality.py` proves each rule by feeding it deliberately broken rows.

### 6. How is `fact_employee` built?
In `load.py`, after DQ each clean employee gets a surrogate `employee_key`; the 20
numeric measures (income, rates, tenure years, satisfaction scores, etc.) are
copied into `fact_employee` with foreign keys to the department/job-role dims and
a mirrored `attrition` flag so measure-only views need no join.

### 7. You target PostgreSQL but develop on SQLite — how do the views stay valid?
`pgserver` has no Windows wheel, so dev uses SQLite and **CI runs real
PostgreSQL 16**. The SQL in `mis/views.sql` is kept portable: `CASE`-based bands
(no dialect date funcs), float division uses `100.0 * ... / NULLIF(...)`, and no
2-arg `ROUND` on floats (Postgres lacks it). A test parses every view as
PostgreSQL via sqlglot.

### 8. Name a few MIS views and the SQL techniques used.
`v_attrition_by_tenure_bucket` and `v_attrition_by_income_band` use `CASE`
bucketing inside a CTE; `v_gender_diversity` uses conditional aggregation
(`SUM(CASE WHEN gender='Female'...)`); every attrition view uses `SUM(attrition)`
(the 1/0 label) over `NULLIF`-guarded division. 11 views in all.

### 9. How does the GenAI assistant turn a question into an answer?
`api/nl2sql.py`: (1) scope/PII check, (2) provider translates to SQL
(`api/providers.py`), (3) guardrails validate+rewrite (`api/guardrails.py`),
(4) execute read-only. Each layer can refuse.

### 10. What exactly do the SQL guardrails enforce?
In `api/guardrails.py`: must parse (sqlglot), be a single statement, be a SELECT
(no write/DDL/command nodes), reference **only allow-listed MIS views**, and
carry a row limit (added or capped). So `dim_employee` is unreachable and
`...; DROP TABLE` is rejected.

### 11. How do you stop the assistant leaking individual employee data?
Two ways: the allow-list excludes all employee-level tables (only aggregate v_*
views are queryable), and `_scope_refusal` rejects questions mentioning names,
employee IDs, "every employee", etc., before any SQL is generated.

### 12. Why a read-only connection if the guardrails already block writes?
Defence in depth. `_read_only_engine` sets `PRAGMA query_only` (SQLite) or
`SET default_transaction_read_only` (Postgres), so even a guardrail bug can't
mutate data. In production this maps to a SELECT-only DB role.

### 13. How is the GenAI assistant evaluated?
`eval/run_eval.py` runs 15 hand-written questions through the full pipeline and
compares each result to a hand-written **reference query** (exact-match on the
rounded result) — measuring whether it routed to the right view with the right
filters. It also fires 10 adversarial prompts and checks all are blocked. Result:
100% / 100% on the mock.

### 14. Isn't 100% accuracy suspicious?
It's honest but scoped: the default provider is a **rule-based mock** so CI is
deterministic and key-free, and the 15 questions exercise exactly the intents it
supports. The mock is a transparent baseline; real generalisation comes from the
switchable Gemini/Ollama providers behind the same guardrails.

### 15. How does provider switching work?
`get_provider()` returns Mock/Gemini/Ollama based on `LLM_PROVIDER`. All return
raw SQL that goes through the *same* guardrails — the LLM is never trusted.
Default is `mock`, so tests and CI need no API key.

### 16. Explain the attrition model's train/test split.
The data has no dates, so an out-of-time split isn't possible; `model/train.py`
uses a **stratified 75/25 hold-out** (fixed seed) that preserves the ~16%
attrition base rate in both folds — the standard way this public dataset is
modelled. No row appears in both folds.

### 17. What features, and which matter most?
The employee's attributes and measures: department, job role, overtime, job level,
income, tenure, distance, and the satisfaction/involvement scores. Permutation
importance puts **overtime, monthly income, stock-option level, job satisfaction,
age and job level** on top — all well-documented real drivers in this dataset.

### 18. The model's AUC is ~0.82 — walk me through the numbers.
The baseline (predict "stays") gets F1 0.00; logistic regression reaches
**ROC-AUC 0.82**, recall **0.64** and F1 0.50 — catching ~two-thirds of leavers at
a ~16% base rate (the usual precision/recall trade-off in attrition). Gradient
boosting is close (AUC 0.78). All numbers are from a real run in `metrics.json`.

### 19. What's the n8n workflow and why is it "deferred"?
`automation/n8n_onboarding_workflow.json`: a new-hire webhook → Code node builds a
department-specific task checklist + welcome email → SMTP to MailHog → responds
with the tasks. n8n + MailHog are Docker-only and Docker isn't available here, so
it's authored/exported/validated but the **live run is deferred** (no fabricated
screenshots).

### 20. How do you know it all works, and what does CI do?
36 pytest tests cover the real-data source, DQ, warehouse, views, guardrails,
NL→SQL, the API, the eval, and the model-beats-baseline check. CI
(`.github/workflows/ci.yml`) runs ruff + the whole suite against a real
PostgreSQL 16 service with the LLM mocked — proving the Postgres path end to end.
