# PeoplePulse — Résumé bullets

Real numbers, ≤25 words each. (Real public data: IBM HR Analytics Employee
Attrition, Kaggle, DbCL-1.0 — 1,470 employees, no real individual's data.)

- Built a people-analytics MIS on a PostgreSQL/SQLite star schema with 11 SQL
  views and data-quality quarantine, over the real IBM HR Attrition dataset
  (1,470 employees).

- Shipped a guard-railed GenAI natural-language-to-SQL HR assistant (sqlglot
  validation, read-only allow-listed views, PII refusals) scoring 100% on 15
  questions and blocking 10/10 adversarial prompts.

- Trained a stratified attrition-risk model (logistic regression + gradient
  boosting, ROC-AUC 0.82, recall 0.64) that beats a majority baseline and
  surfaces overtime, income and job level as top drivers.

- Delivered Streamlit + Power BI (DAX) dashboards and a low-code n8n onboarding
  workflow, with 36 tests and CI running on PostgreSQL 16.
