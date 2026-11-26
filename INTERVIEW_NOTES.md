# PeoplePulse — Interview Notes

20 questions and answers tied to specific files/functions. All data is SYNTHETIC.

### 1. What is PeoplePulse in one sentence?
A people-analytics MIS over synthetic HRIS data with a guard-railed GenAI
natural-language-to-SQL assistant, an attrition-risk model, and a low-code
onboarding workflow — covering analytics, dashboards, GenAI, low-code, and
governance.

### 2. Why synthetic data, and how is it generated?
To avoid any real HR/PII data. `peoplepulse/data/generate.py` creates ~2,000
employees over 3 years across India/UAE/Germany with departments, grades, comp
bands, performance ratings, exits, and a hiring funnel — all seeded (seed 42) so
runs are reproducible.

### 3. How do you make the attrition signal realistic instead of random?
Each employee gets a latent **annual risk** from a logistic function of
department, grade and pay (`generate_employees`), and exits are drawn from a
**monthly hazard** (`1-(1-risk)^(1/12)`). The same risk also lowers performance
ratings, reproducing "low performers / underpaid leave more". A purely random
exit would wash out the signal.

### 4. Walk me through the warehouse schema.
A Kimball star in `peoplepulse/warehouse/schema.py`: `dim_date`,
`dim_department`, `dim_country`, `dim_employee`, and facts
`fact_headcount_monthly`, `fact_exits`, `fact_hiring_funnel`, plus a
`quarantine` table. Surrogate keys are assigned in Python so DDL and inserts are
identical on SQLite and Postgres.

### 5. What data-quality checks run, and what happens to bad rows?
`peoplepulse/warehouse/quality.py` checks null IDs, duplicate IDs, unparseable
hire dates, exit-before-hire, and unknown country codes. Bad rows are **not
dropped** — they go to the `quarantine` table with a reason. The generator
injects exactly 8 dirty rows so the quarantine count is verifiable (tested).

### 6. How is the headcount fact derived?
In `load.py`, for each month-end an employee is counted if hired on/before it and
not yet exited (`exit_date > month_end`). Grain is month × department × country ×
grade × gender, so one fact serves headcount, diversity, and segment attrition.

### 7. You target PostgreSQL but develop on SQLite — how do the views stay valid?
`pgserver` has no Windows wheel, so dev uses SQLite and **CI runs real
PostgreSQL 16**. The SQL in `mis/views.sql` is kept portable: date parts live in
`dim_date` (no `date_trunc`/`strftime`), float division uses `100.0 * ... /
NULLIF(...)`, and no 2-arg `ROUND` on floats (Postgres lacks it). A test parses
every view as PostgreSQL via sqlglot.

### 8. Name a few MIS views and the SQL techniques used.
`v_attrition_monthly` uses a CTE + `LAG()` + a framed window
(`ROWS BETWEEN 11 PRECEDING AND CURRENT ROW`) for rolling-12-month attrition;
`v_tenure_buckets` uses `CASE` bucketing; `v_gender_diversity_by_grade` uses
conditional aggregation against the latest snapshot.

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
`eval/run_eval.py` runs 25 hand-written questions through the full pipeline and
compares each result to a hand-written **reference query** (exact-match on the
rounded result) — measuring whether it routed to the right view with the right
filters. It also fires 10 adversarial prompts and checks all are blocked. Result:
100% / 100% on the mock.

### 14. Isn't 100% accuracy suspicious?
It's honest but scoped: the default provider is a **rule-based mock** so CI is
deterministic and key-free, and the 25 questions exercise exactly the intents it
supports. The mock is a transparent baseline; real generalisation comes from the
switchable Gemini/Ollama providers behind the same guardrails.

### 15. How does provider switching work?
`get_provider()` returns Mock/Gemini/Ollama based on `LLM_PROVIDER`. All return
raw SQL that goes through the *same* guardrails — the LLM is never trusted.
Default is `mock`, so tests and CI need no API key.

### 16. Explain the attrition model's train/test split.
Out-of-time (`model/train.py`): train snapshot as-of 2023-12-31 labelled by exits
in 2024; test snapshot as-of 2024-12-31 labelled by exits in 2025. Non-overlapping
forward windows prevent leakage — unlike a random shuffle.

### 17. What features, and which matter most?
Tenure, grade, comp-ratio (pay vs band midpoint), department, country, gender,
and as-of performance rating. Feature importance shows **comp-ratio and
department** dominate — exactly the drivers built into the synthetic hazard, and
gender/country are ~0 (as intended).

### 18. The model's AUC is ~0.63 — is that good?
It's honest. The baseline (predict "stays") gets F1 0.00; the model reaches F1
~0.33 and recall ~0.56, catching over half of future leavers at a low (~18%) base
rate — the typical precision/recall trade-off in attrition. I report real numbers,
not an inflated AUC.

### 19. What's the n8n workflow and why is it "deferred"?
`automation/n8n_onboarding_workflow.json`: a new-hire webhook → Code node builds a
department-specific task checklist + welcome email → SMTP to MailHog → responds
with the tasks. n8n + MailHog are Docker-only and Docker isn't available here, so
it's authored/exported/validated but the **live run is deferred** (no fabricated
screenshots).

### 20. How do you know it all works, and what does CI do?
34 pytest tests cover generation, DQ, warehouse, views, guardrails, NL→SQL, the
API, the eval, and the model-beats-baseline check. CI
(`.github/workflows/ci.yml`) runs ruff + the whole suite against a real
PostgreSQL 16 service with the LLM mocked — proving the Postgres path end to end.
