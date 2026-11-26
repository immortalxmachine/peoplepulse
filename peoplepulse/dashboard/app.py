"""Streamlit MIS dashboard over the PeoplePulse warehouse views.

Reads only the MIS v_* views (never base tables), so the dashboard shows exactly
the same governed metrics as the GenAI assistant and Power BI.

Data: REAL IBM HR Analytics Employee Attrition (cross-sectional, 1,470 staff).

Run:  streamlit run peoplepulse/dashboard/app.py --server.port 8501
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

from peoplepulse.config import database_url

st.set_page_config(page_title="PeoplePulse", page_icon="📊", layout="wide")


@st.cache_resource
def get_engine():
    return create_engine(database_url())


@st.cache_data
def q(sql: str) -> pd.DataFrame:
    with get_engine().connect() as conn:
        return pd.read_sql(text(sql), conn)


st.title("📊 PeoplePulse — People Analytics MIS")
st.caption(
    "Data: **real** IBM HR Analytics Employee Attrition dataset "
    "(Kaggle · DbCL-1.0 · 1,470 employees of a fictional company — a public "
    "teaching dataset, no real individual's data). Metrics come from governed "
    "SQL views in the warehouse."
)

# --- KPI row -----------------------------------------------------------------
overall = q("SELECT total_employees, leavers, attrition_pct FROM v_attrition_overall")
income = q(
    "SELECT SUM(avg_monthly_income * employees) / NULLIF(SUM(employees), 0) AS v "
    "FROM v_income_by_department"
)
ot = q("SELECT attrition_pct AS v FROM v_attrition_by_overtime WHERE overtime = 'Yes'")

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Employees", f"{int(overall['total_employees'][0]):,}")
c2.metric("Attrition (overall)", f"{overall['attrition_pct'][0]:.1f}%")
c3.metric("Leavers", f"{int(overall['leavers'][0]):,}")
c4.metric("Avg monthly income", f"${income['v'][0]:,.0f}")
c5.metric("Attrition · overtime", f"{ot['v'][0]:.1f}%")

st.divider()

# --- Attrition drivers -------------------------------------------------------
left, right = st.columns(2)

with left:
    st.subheader("Attrition by department (%)")
    d = q(
        "SELECT department_name, attrition_pct FROM v_attrition_by_department "
        "ORDER BY attrition_pct DESC"
    )
    st.bar_chart(d, x="department_name", y="attrition_pct", height=280)

with right:
    st.subheader("Attrition by job role (%)")
    r = q(
        "SELECT job_role, attrition_pct FROM v_attrition_by_job_role "
        "ORDER BY attrition_pct DESC"
    )
    st.bar_chart(r, x="job_role", y="attrition_pct", height=280)

left2, right2 = st.columns(2)

with left2:
    st.subheader("Attrition by overtime (%)")
    o = q("SELECT overtime, attrition_pct FROM v_attrition_by_overtime ORDER BY overtime")
    st.bar_chart(o, x="overtime", y="attrition_pct", height=280)

with right2:
    st.subheader("Attrition by job level (%)")
    jl = q("SELECT job_level, attrition_pct FROM v_attrition_by_job_level ORDER BY job_level")
    st.bar_chart(jl, x="job_level", y="attrition_pct", height=280)

left3, right3 = st.columns(2)

with left3:
    st.subheader("Attrition by tenure at company (%)")
    tb = q(
        "SELECT tenure_bucket, attrition_pct FROM v_attrition_by_tenure_bucket "
        "ORDER BY bucket_order"
    )
    st.bar_chart(tb, x="tenure_bucket", y="attrition_pct", height=280)

with right3:
    st.subheader("Attrition by monthly-income band (%)")
    ib = q(
        "SELECT income_band, attrition_pct FROM v_attrition_by_income_band "
        "ORDER BY band_order"
    )
    st.bar_chart(ib, x="income_band", y="attrition_pct", height=280)

st.divider()

left4, right4 = st.columns(2)

with left4:
    st.subheader("Avg satisfaction — stayers vs leavers")
    sat = q(
        "SELECT CASE WHEN attrition = 1 THEN 'Left' ELSE 'Stayed' END AS status, "
        "avg_job_satisfaction, avg_work_life_balance, avg_job_involvement "
        "FROM v_satisfaction_by_attrition ORDER BY attrition"
    )
    st.bar_chart(
        sat,
        x="status",
        y=["avg_job_satisfaction", "avg_work_life_balance", "avg_job_involvement"],
        height=280,
    )

with right4:
    st.subheader("Gender diversity by department (% female)")
    gd = q(
        "SELECT department_name, female_pct FROM v_gender_diversity "
        "ORDER BY female_pct DESC"
    )
    st.bar_chart(gd, x="department_name", y="female_pct", height=280)
