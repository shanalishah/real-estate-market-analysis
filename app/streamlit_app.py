# app/streamlit_app.py
from __future__ import annotations
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st

# ---------------- Page & Paths ----------------
st.set_page_config(page_title="CRE Market & Development Analysis", layout="wide")
st.title("Commercial Real Estate Market & Development Analysis")
st.caption("Market KPI screening, composite development score, New Hope Class B summary, and a unit-mix explorer.")

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ANALYSIS_XLSX = ROOT / "analysis" / "CRE_Data_SpringA2025_Analysis.xlsx"

FILES: Dict[str, Path] = {
    "City Summary": DATA / "City_Level_Market_Summary.csv",
    "Development Potential": DATA / "City_Development_Potential.csv",
    "New Hope Class B": DATA / "New_Hope_Class_B_Analysis.csv",
    "New Hope Unit Rents": DATA / "New_Hope_Class_B_Unit_Data.csv",
}

# Skyline memo assumptions (used in Unit-Mix Explorer)
TOTAL_UNITS = 85
TOTAL_SF = 80_000
SF_STUDIO = 800
SF_1BR = 1200
FIXED_COST_YR = 320_000
VAR_COST_STUDIO_MO = 720
VAR_COST_1BR_MO = 1_000

# Market caps by rent ranges from the memo (studios / 1BR)
CAP_TABLE = [
    ((-np.inf, 1499), 60, 75),
    ((1500, 1800), 55, 70),
    ((1800, 2100), 48, 65),
    ((2200, 2500), 40, 57),
    ((2500, 2800), 30, 48),
    ((2800, 3100), 18, 35),
]

# ---------------- Helpers ----------------
@st.cache_data(show_spinner=False)
def read_csv(path: Path) -> Optional[pd.DataFrame]:
    if not path.exists(): return None
    for enc in (None, "utf-8", "latin1"):
        try:
            return pd.read_csv(path, encoding=enc) if enc else pd.read_csv(path)
        except Exception:
            continue
    return None

@st.cache_data(show_spinner=False)
def read_excel_preview(path: Path, nrows: int = 12) -> Dict[str, pd.DataFrame]:
    out: Dict[str, pd.DataFrame] = {}
    if not path.exists(): return out
    try:
        xls = pd.ExcelFile(path)
        for sh in xls.sheet_names[:4]:
            try:
                out[sh] = xls.parse(sh, nrows=nrows)
            except Exception:
                pass
    except Exception:
        pass
    return out

def development_score(
    df: pd.DataFrame,
    w_noi: float = 0.40,
    w_cagr: float = 0.30,
    w_vac: float = 0.15,
    w_exp: float = 0.15,
    noi_col="Avg NOI",
    cagr_col="Avg Rent CAGR",
    vac_col="Avg Vacancy",
    expenses_col: Optional[str] = None,
    expense_ratio_col: Optional[str] = None,
) -> pd.DataFrame:
    """Compute a z-scored composite: +NOI, +CAGR, −Vacancy, −Expenses/Expense Ratio."""
    out = df.copy()
    def z(x): x = pd.to_numeric(x, errors="coerce"); return (x - x.mean())/ (x.std(ddof=0) if x.std(ddof=0) else 1)
    z_noi = z(out[noi_col])
    z_cagr = z(out[cagr_col])
    z_vac = z(out[vac_col])
    # prefer expense ratio if present
    if expense_ratio_col and expense_ratio_col in out.columns:
        z_exp = z(out[expense_ratio_col])
    elif expenses_col and expenses_col in out.columns:
        z_exp = z(out[expenses_col])
    else:
        z_exp = pd.Series(0, index=out.index)

    out["Development Score"] = (
        w_noi * z_noi + w_cagr * z_cagr - w_vac * z_vac - w_exp * z_exp
    )
    return out

def cap_by_rent(rent: float, is_studio: bool) -> int:
    for (lo, hi), cap_s, cap_1b in CAP_TABLE:
        if lo < rent <= hi:
            return cap_s if is_studio else cap_1b
    # if above last band, use last band cap
    return CAP_TABLE[-1][1 if is_studio else 2]

def fmt_pct(x) -> str:
    try:
        return f"{float(x):.1%}"
    except Exception:
        return "—"

def fmt_money(x) -> str:
    try:
        return f"${float(x):,.0f}"
    except Exception:
        return "—"

# ---------------- Tabs ----------------
tab_overview, tab_kpis, tab_score, tab_newhope, tab_units, tab_workbook = st.tabs(
    ["Overview", "City KPIs", "Composite Score", "New Hope Class B", "Unit-Mix Explorer", "Workbook Preview"]
)

# -------- Overview --------
with tab_overview:
    st.subheader("Files Detected")
    c1, c2 = st.columns(2)
    with c1:
        for label, p in FILES.items():
            st.write(f"- **{label}:** `{p.name}` — " + ("✅ found" if p.exists() else "❌ missing"))
    with c2:
        st.write(f"- **Excel model:** `{ANALYSIS_XLSX.name}` — " + ("✅ found" if ANALYSIS_XLSX.exists() else "❌ missing"))

    st.divider()
    st.subheader("Executive Summary")
    df_city = read_csv(FILES["City Summary"])
    df_dev  = read_csv(FILES["Development Potential"])
    df_b    = read_csv(FILES["New Hope Class B"])

    bullets = []
    if isinstance(df_dev, pd.DataFrame) and not df_dev.empty:
        # Build a default score using expense ratio if available
        if "Avg Expense Ratio" in df_dev.columns:
            scored = development_score(df_dev, expense_ratio_col="Avg Expense Ratio")
        else:
            scored = development_score(df_city, expenses_col="Avg Expenses") if isinstance(df_city, pd.DataFrame) else None
        if isinstance(scored, pd.DataFrame):
            top = scored.sort_values("Development Score", ascending=False).iloc[0]
            bullets.append(f"**Highest development score:** {top['City']}.")

    if isinstance(df_b, pd.DataFrame) and not df_b.empty:
        row_b = df_b[df_b["Class"].astype(str).str.upper().eq("B")]
        if not row_b.empty:
            r = row_b.iloc[0]
            bullets.append(
                f"**New Hope – Class B:** NOI {fmt_money(r['Avg NOI'])} · "
                f"Rent CAGR {fmt_pct(r['Avg Rent CAGR'])} · "
                f"Vacancy {fmt_pct(r['Avg Vacancy Rate'])} · "
                f"Expense Ratio {fmt_pct(r['Avg Expense Ratio'])}"
            )

    if bullets:
        for b in bullets: st.write("• " + b)
        st.info(
            "Markets are screened via NOI, Rent CAGR, Vacancy, and cost burden. "
            "New Hope emerges as the most balanced, return-focused option under our assumptions."
        )
    else:
        st.info("Add CSVs to `/data` to populate the summary.")

# -------- City KPIs --------
with tab_kpis:
    st.subheader("City-level KPIs")
    df = read_csv(FILES["City Summary"])
    if df is None or df.empty:
        st.info("Upload `City_Level_Market_Summary.csv` into `/data`.")
    else:
        view = df.copy()
        # nice formatting for display
        for c in view.columns:
            if "Rent CAGR" in c or "Vacancy" in c:
                view[c] = (pd.to_numeric(view[c], errors="coerce")*100).round(1)
        st.dataframe(view, use_container_width=True)

        city_col = "City"
        kpi_cols = [c for c in view.columns if c != city_col]
        left, right = st.columns([2,1])
        with right:
            metric = st.selectbox("Sort by KPI", kpi_cols, index=0)
        with left:
            chart_df = df[[city_col, metric]].copy()
            # scale % metrics for chart readability
            if any(k in metric.lower() for k in ["vacancy", "cagr", "ratio", "%"]):
                chart_df[metric] = pd.to_numeric(chart_df[metric], errors="coerce")*100
            st.markdown(f"**Top Markets by {metric}**")
            st.bar_chart(chart_df.set_index(city_col))

# -------- Composite Score --------
with tab_score:
    st.subheader("Composite Development Score (adjust weights)")
    df_city = read_csv(FILES["City Summary"])
    df_dev  = read_csv(FILES["Development Potential"])

    if (df_city is None or df_city.empty) and (df_dev is None or df_dev.empty):
        st.info("Upload city CSVs to compute a score.")
    else:
        source = st.radio("Data source", ["City Summary", "Development Potential"], horizontal=True)
        base = df_dev if (source == "Development Potential" and isinstance(df_dev, pd.DataFrame)) else df_city

        w_noi  = st.slider("Weight: NOI",       0.0, 1.0, 0.40, 0.05)
        w_cagr = st.slider("Weight: Rent CAGR", 0.0, 1.0, 0.30, 0.05)
        w_vac  = st.slider("Weight: Vacancy",   0.0, 1.0, 0.15, 0.05)
        w_exp  = st.slider("Weight: Expenses/Expense Ratio", 0.0, 1.0, 0.15, 0.05)

        scored = development_score(
            base,
            w_noi=w_noi, w_cagr=w_cagr, w_vac=w_vac, w_exp=w_exp,
            noi_col="Avg NOI",
            cagr_col="Avg Rent CAGR",
            vac_col="Avg Vacancy" if "Avg Vacancy" in base.columns else "Avg Vacancy Rate",
            expenses_col="Avg Expenses" if "Avg Expenses" in base.columns else None,
            expense_ratio_col="Avg Expense Ratio" if "Avg Expense Ratio" in base.columns else None,
        )
        ranked = scored.sort_values("Development Score", ascending=False)
        st.dataframe(ranked, use_container_width=True)
        st.success(f"Top market by current weights: **{ranked.iloc[0]['City']}**")

# -------- New Hope Class B --------
with tab_newhope:
    st.subheader("New Hope – Class B Summary")
    df_b = read_csv(FILES["New Hope Class B"])
    if df_b is None or df_b.empty:
        st.info("Upload `New_Hope_Class_B_Analysis.csv` to `/data`.")
    else:
        view = df_b.copy()
        for c in ["Avg Rent CAGR", "Avg Vacancy Rate", "Avg Expense Ratio"]:
            if c in view.columns:
                view[c] = (pd.to_numeric(view[c], errors="coerce")*100).round(2).astype(str) + "%"
        st.dataframe(view, use_container_width=True)

# -------- Unit-Mix Explorer --------
with tab_units:
    st.subheader("Unit-Mix Explorer (New Hope, Class B)")
    df_unit = read_csv(FILES["New Hope Unit Rents"])
    if df_unit is None or df_unit.empty:
        st.info("Upload `New_Hope_Class_B_Unit_Data.csv` to `/data`.")
    else:
        r_studio = float(df_unit["Avg Studio Rent"].iloc[0])
        r_1br    = float(df_unit["Avg 1-Bedroom Rent"].iloc[0])
        vac_rate = float(df_unit["Avg Vacancy Rate"].iloc[0])  # ~10%
        exp_ratio = float(df_unit["Avg Expense Ratio"].iloc[0])  # ~50%

        c1, c2, c3 = st.columns(3)
        with c1:
            n_st = st.number_input("Studios", min_value=0, max_value=TOTAL_UNITS, value=55, step=1)
        with c2:
            n_1b = st.number_input("1-Bedrooms", min_value=0, max_value=TOTAL_UNITS, value=30, step=1)
        with c3:
            st.caption("Constraints from Skyline memo: 85 units, 80k sq ft, Studio:800sf, 1BR:1200sf.")

        # enforce total units
        if n_st + n_1b != TOTAL_UNITS:
            st.warning(f"Total units must equal {TOTAL_UNITS}. Currently: {n_st + n_1b}")

        # floor-area constraint
        used_sf = n_st*SF_STUDIO + n_1b*SF_1BR
        if used_sf > TOTAL_SF:
            st.error(f"Floor area exceeded: {used_sf:,} sf > {TOTAL_SF:,} sf")

        # market caps based on rent bands
        cap_st = cap_by_rent(r_studio, is_studio=True)
        cap_1b = cap_by_rent(r_1br, is_studio=False)

        # leased units: respect caps and vacancy (two effects combined)
        leased_st = min(n_st, cap_st) * (1 - vac_rate)
        leased_1b = min(n_1b, cap_1b) * (1 - vac_rate)

        rev_year = 12*(leased_st*r_studio + leased_1b*r_1br)

        # costs: fixed annual + variable monthly per unit * 12
        var_cost = 12*(n_st*VAR_COST_STUDIO_MO + n_1b*VAR_COST_1BR_MO)
        opex_year = FIXED_COST_YR + var_cost

        noi_year = rev_year - opex_year

        # display metrics
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("Avg Studio Rent", f"${r_studio:,.0f}")
        m2.metric("Avg 1BR Rent", f"${r_1br:,.0f}")
        m3.metric("Vacancy Assumption", f"{vac_rate*100:.1f}%")
        m4.metric("Leased Studios (cap)", f"{leased_st:,.1f}  (cap {cap_st})")
        m5.metric("Leased 1BRs (cap)", f"{leased_1b:,.1f}  (cap {cap_1b})")
        m6.metric("Used Floor Area", f"{used_sf:,.0f} sf")

        st.markdown("**Pro-Forma (Annual)**")
        tdf = pd.DataFrame({
            "Metric": ["Revenue", "Operating Expenses", "NOI", "Fixed Costs", "Variable Costs (annual)"],
            "Amount": [rev_year, opex_year, noi_year, FIXED_COST_YR, var_cost]
        })
        tdf["Amount"] = tdf["Amount"].map(lambda x: f"${x:,.0f}")
        st.table(tdf)

        if n_st > cap_st:
            st.info(f"Studio market capacity binding at current rent band: cap {cap_st}.")
        if n_1b > cap_1b:
            st.info(f"1-Bedroom market capacity binding at current rent band: cap {cap_1b}.")

# -------- Workbook Preview --------
with tab_workbook:
    st.subheader("Workbook Preview")
    previews = read_excel_preview(ANALYSIS_XLSX)
    if previews:
        for i, (sheet, df_sh) in enumerate(previews.items()):
            st.markdown(f"**Sheet:** {sheet}")
            st.dataframe(df_sh, use_container_width=True)
    else:
        st.info("Upload your Excel workbook to `/analysis` to preview sheets.")
