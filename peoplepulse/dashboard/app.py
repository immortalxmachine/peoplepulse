"""Streamlit MIS dashboard over the PeoplePulse warehouse views.

Reads only the MIS v_* views (never base tables), so the dashboard shows exactly
the same governed metrics as the GenAI assistant and Power BI.

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
    "⚠️ All data is **SYNTHETIC** (randomly generated). No real employee data. "
    "Metrics come from governed SQL views in the warehouse."
)

# --- KPI row -----------------------------------------------------------------
latest_hc = q("SELECT total_headcount FROM v_headcount_trend ORDER BY date_key DESC LIMIT 1")
latest_attr = q(
    "SELECT rolling_12m_attrition_pct FROM v_attrition_monthly ORDER BY date_key DESC LIMIT 1"
)
tth = q(
    "SELECT SUM(avg_time_to_hire_days * hires) / NULLIF(SUM(hires), 0) AS v "
    "FROM v_time_to_hire"
)
oa = q("SELECT 100.0 * SUM(accepts) / NULLIF(SUM(offers), 0) AS v FROM v_offer_acceptance")
vol = q("SELECT SUM(exits) AS v FROM v_exits_by_type WHERE exit_type = 'Voluntary'")

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Current headcount", f"{int(latest_hc['total_headcount'][0]):,}")
c2.metric("Attrition (rolling 12m)", f"{latest_attr['rolling_12m_attrition_pct'][0]:.1f}%")
c3.metric("Avg time-to-hire", f"{tth['v'][0]:.0f} days")
c4.metric("Offer acceptance", f"{oa['v'][0]:.0f}%")
c5.metric("Voluntary exits (all-time)", f"{int(vol['v'][0]):,}")

st.divider()

# --- Trends ------------------------------------------------------------------
left, right = st.columns(2)

with left:
    st.subheader("Headcount trend")
    hc = q("SELECT year_month, total_headcount FROM v_headcount_trend ORDER BY date_key")
    st.line_chart(hc, x="year_month", y="total_headcount", height=280)

with right:
    st.subheader("Attrition rate (%)")
    at = q(
        "SELECT year_month, monthly_attrition_pct, rolling_12m_attrition_pct "
        "FROM v_attrition_monthly ORDER BY date_key"
    )
    st.line_chart(
        at, x="year_month", y=["monthly_attrition_pct", "rolling_12m_attrition_pct"], height=280
    )

left2, right2 = st.columns(2)

with left2:
    st.subheader("Exits: voluntary vs involuntary")
    et = q("SELECT exit_type, SUM(exits) AS exits FROM v_exits_by_type GROUP BY exit_type")
    st.bar_chart(et, x="exit_type", y="exits", height=280)

with right2:
    st.subheader("Tenure at exit")
    tb = q("SELECT tenure_bucket, exits FROM v_tenure_buckets ORDER BY bucket_order")
    st.bar_chart(tb, x="tenure_bucket", y="exits", height=280)

left3, right3 = st.columns(2)

with left3:
    st.subheader("Gender diversity by grade (% female)")
    gd = q("SELECT grade, female_pct FROM v_gender_diversity_by_grade ORDER BY grade")
    st.bar_chart(gd, x="grade", y="female_pct", height=280)

with right3:
    st.subheader("Avg time-to-hire by department")
    tth_dept = q(
        "SELECT department_name, "
        "SUM(avg_time_to_hire_days * hires) / NULLIF(SUM(hires), 0) AS days "
        "FROM v_time_to_hire GROUP BY department_name ORDER BY days DESC"
    )
    st.bar_chart(tth_dept, x="department_name", y="days", height=280)

st.divider()
st.subheader("Attrition by country & department (latest full year)")
seg = q(
    "SELECT country_name, department_name, "
    "100.0 * SUM(exits) / NULLIF(AVG(end_headcount), 0) AS attrition_pct "
    "FROM v_attrition_by_segment WHERE year = (SELECT MAX(year) FROM v_attrition_by_segment) "
    "GROUP BY country_name, department_name"
)
pivot = seg.pivot(index="department_name", columns="country_name", values="attrition_pct")
st.dataframe(pivot.style.format("{:.1f}%").background_gradient(cmap="Reds"), height=330)
