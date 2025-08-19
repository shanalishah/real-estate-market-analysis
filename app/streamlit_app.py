# app/streamlit_app.py
from __future__ import annotations
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st
import altair as alt

# ==============================
# Page / Paths
# ==============================
st.set_page_config(page_title="Commercial Real Estate Market & Development Analysis", layout="wide")

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ANALYSIS_XLSX = ROOT / "analysis" / "CRE_Data_SpringA2025_Analysis.xlsx"

FILES: Dict[str, Path] = {
    "City Summary": DATA / "City_Level_Market_Summary.csv",
    "Development Potential": DATA / "City_Development_Potential.csv",
    "New Hope Class B": DATA / "New_Hope_Class_B_Analysis.csv",
    "New Hope Unit Rents": DATA / "New_Hope_Class_B_Unit_Data.csv",
}

# Skyline memo core assumptions (used in Unit-Mix):
TOTAL_UNITS = 85
TOTAL_SF = 80_000
SF_STUDIO = 800
SF_1BR = 1200
FIXED_COST_YR = 320_000
VAR_COST_STUDIO_MO = 720
VAR_COST_1BR_MO = 1_000

# Market capacity by rent band (studios cap, 1BR cap)
CAP_TABLE = [
    ((-np.inf, 1499), 60, 75),
    ((1500, 1800), 55, 70),
    ((1800, 2100), 48, 65),
    ((2200, 2500), 40, 57),
    ((2500, 2800), 30, 48),
    ((2800, 3100), 18, 35),
]

# ==============================
# Utilities
# ==============================
@st.cache_data(show_spinner=False)
def read_csv(path: Path) -> Optional[pd.DataFrame]:
    if not path.exists():
        return None
    for enc in (None, "utf-8", "latin1"):
        try:
            return pd.read_csv(path, encoding=enc) if enc else pd.read_csv(path)
        except Exception:
            continue
    return None

@st.cache_data(show_spinner=False)
def read_excel_preview(path: Path) -> Dict[str, pd.DataFrame]:
    """Return all sheets as small previews; used with a picker."""
    out: Dict[str, pd.DataFrame] = {}
    if not path.exists():
        return out
    try:
        xls = pd.ExcelFile(path)
        for sh in xls.sheet_names:
            try:
                out[sh] = xls.parse(sh, nrows=12)
            except Exception:
                pass
    except Exception:
        pass
    return out

def show_df(df: pd.DataFrame):
    """Render DataFrame safely: stringify column names to avoid Arrow mixed-type warnings."""
    if df is None:
        return
    df = df.copy()
    try:
        df.columns = df.columns.astype(str)
    except Exception:
        pass
    st.dataframe(df, use_container_width=True)

def zscore(s: pd.Series) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce")
    sd = s.std(ddof=0)
    return (s - s.mean()) / (sd if sd and sd != 0 else 1)

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
    out = df.copy()
    z_noi = zscore(out[noi_col]) if noi_col in out.columns else 0
    z_cagr = zscore(out[cagr_col]) if cagr_col in out.columns else 0
    z_vac = zscore(out[vac_col]) if vac_col in out.columns else 0
    if expense_ratio_col and expense_ratio_col in out.columns:
        z_exp = zscore(out[expense_ratio_col])
    elif expenses_col and expenses_col in out.columns:
        z_exp = zscore(out[expenses_col])
    else:
        z_exp = 0
    out["Development Score"] = w_noi*z_noi + w_cagr*z_cagr - w_vac*z_vac - w_exp*z_exp
    return out

def cap_by_rent(rent: float, is_studio: bool) -> int:
    for (lo, hi), cap_s, cap_1b in CAP_TABLE:
        if lo < rent <= hi:
            return cap_s if is_studio else cap_1b
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

def unit_mix_metrics(n_st: int, n_1br: int, r_st: float, r_1br: float, vac: float) -> dict:
    """Compute revenue, opex, NOI with caps, vacancy, fixed & variable costs."""
    used_sf = n_st*SF_STUDIO + n_1br*SF_1BR
    cap_st = cap_by_rent(r_st, is_studio=True)
    cap_1b = cap_by_rent(r_1br, is_studio=False)
    leased_st = min(n_st, cap_st) * (1 - vac)
    leased_1b = min(n_1br, cap_1b) * (1 - vac)
    rev_year = 12*(leased_st*r_st + leased_1b*r_1br)
    var_cost = 12*(n_st*VAR_COST_STUDIO_MO + n_1br*VAR_COST_1BR_MO)
    opex_year = FIXED_COST_YR + var_cost
    noi_year = rev_year - opex_year
    return dict(
        used_sf=used_sf, cap_st=cap_st, cap_1b=cap_1b,
        leased_st=leased_st, leased_1b=leased_1b,
        revenue=rev_year, var_cost=var_cost, opex=opex_year, noi=noi_year
    )

def optimize_mix(r_st: float, r_1br: float, vac: float) -> Tuple[int, int, dict]:
    """Brute-force search: max NOI under unit & floor constraints."""
    best = None
    best_tuple = (0, 0)
    for n_st in range(TOTAL_UNITS+1):
        n_1br = TOTAL_UNITS - n_st
        if n_st*SF_STUDIO + n_1br*SF_1BR > TOTAL_SF:
            continue
        m = unit_mix_metrics(n_st, n_1br, r_st, r_1br, vac)
        if (best is None) or (m["noi"] > best["noi"]):
            best = m; best_tuple = (n_st, n_1br)
    return best_tuple[0], best_tuple[1], best or {}

# ==============================
# Sidebar (professional tone)
# ==============================
with st.sidebar:
    st.header("Project Context")
    st.write(
        "- Market screening → composite scoring → development selection\n"
        "- Financial feasibility with constraints and sensitivity analysis\n"
        "- Excel-first analysis, presented via Streamlit"
    )
    # Accurate, document-backed skills
    st.markdown("**Skills Demonstrated**")
    st.write(
        "- Data analysis & KPI engineering\n"
        "- Financial modeling (pro forma)\n"
        "- Scenario & sensitivity analysis\n"
        "- Comparative market analysis\n"
        "- Prescriptive optimization (constraints & mix)"
    )
    st.markdown("---")

# ==============================
# Tabs
# ==============================
st.title("Commercial Real Estate Market & Development Analysis")
tabs = st.tabs(["Overview", "City KPIs", "Composite Score", "New Hope Class B", "Unit-Mix & Valuation", "Workbook Preview"])

# -------- Overview --------
with tabs[0]:
    st.subheader("What This App Shows")
    st.write(
        "This tool summarizes the market screening and development feasibility workflow for a Class B multifamily asset. "
        "**City Summary** provides the current-state snapshot (NOI, vacancy, expense levels); "
        "**Development Potential** is a forward-looking view emphasizing growth and feasibility."
    )

    st.subheader("Files Detected")
    c1, c2 = st.columns(2)
    with c1:
        for label, p in FILES.items():
            st.write(f"- **{label}:** `{p.name}` — " + ("✅ found" if p.exists() else "❌ missing"))
    with c2:
        st.write(f"- **Excel workbook:** `{ANALYSIS_XLSX.name}` — " + ("✅ found" if ANALYSIS_XLSX.exists() else "❌ missing"))

    st.divider()
    st.subheader("Executive Summary")
    df_city = read_csv(FILES["City Summary"])
    df_dev  = read_csv(FILES["Development Potential"])
    df_b    = read_csv(FILES["New Hope Class B"])

    bullets = []
    if isinstance(df_dev, pd.DataFrame) and not df_dev.empty:
        if "Avg Expense Ratio" in df_dev.columns:
            scored = development_score(df_dev, expense_ratio_col="Avg Expense Ratio")
        elif isinstance(df_city, pd.DataFrame):
            scored = development_score(df_city, expenses_col="Avg Expenses")
        else:
            scored = None
        if isinstance(scored, pd.DataFrame) and "City" in scored.columns:
            top_city = scored.sort_values("Development Score", ascending=False).iloc[0]["City"]
            bullets.append(f"**Highest composite development score:** {top_city}.")

    if isinstance(df_b, pd.DataFrame) and not df_b.empty:
        row_b = df_b[df_b["Class"].astype(str).str.upper().eq("B")]
        if not row_b.empty:
            r = row_b.iloc[0]
            bullets.append(
                f"**New Hope – Class B:** NOI {fmt_money(r.get('Avg NOI'))} · "
                f"Rent CAGR {fmt_pct(r.get('Avg Rent CAGR'))} · "
                f"Vacancy {fmt_pct(r.get('Avg Vacancy Rate'))} · "
                f"Expense Ratio {fmt_pct(r.get('Avg Expense Ratio'))}"
            )

    if bullets:
        for b in bullets:
            st.write("• " + b)
        st.info("New Hope emerges as a balanced, return-focused option under the current assumptions.")
    else:
        st.info("Upload the CSVs to populate the summary.")

# -------- City KPIs (with scatter visual) --------
with tabs[1]:
    st.subheader("City-Level KPIs (Current-State Snapshot)")
    st.caption("Compare cities on observed metrics such as NOI, vacancy, and rent growth.")
    df = read_csv(FILES["City Summary"])
    if df is None or df.empty:
        st.info("Upload `City_Level_Market_Summary.csv` into `/data`.")
    else:
        dfn = df.copy()
        for c in ["Avg Rent CAGR", "Avg Vacancy"]:
            if c in dfn.columns:
                dfn[c] = pd.to_numeric(dfn[c], errors="coerce")
        show_df(
            dfn.assign(
                **{
                    "Avg Rent CAGR (%)": (dfn["Avg Rent CAGR"]*100).round(1) if "Avg Rent CAGR" in dfn.columns else None,
                    "Avg Vacancy (%)": (dfn["Avg Vacancy"]*100).round(1) if "Avg Vacancy" in dfn.columns else None
                }
            )
        )
        st.download_button("Download City KPIs CSV", data=df.to_csv(index=False), file_name="City_KPIs.csv", use_container_width=True)

        # Scatter: NOI vs Vacancy, size by Rent CAGR
        if all(c in dfn.columns for c in ["Avg NOI", "Avg Vacancy", "Avg Rent CAGR", "City"]):
            c_scatter = alt.Chart(dfn).mark_circle().encode(
                x=alt.X("Avg NOI:Q", title="Average NOI ($)"),
                y=alt.Y("Avg Vacancy:Q", title="Average Vacancy (0–1)"),
                size=alt.Size("Avg Rent CAGR:Q", title="Rent CAGR (0–1)", legend=None),
                color=alt.Color("City:N", legend=None),
                tooltip=["City", "Avg NOI", "Avg Vacancy", "Avg Rent CAGR"]
            ).properties(height=360)
            st.markdown("**NOI vs. Vacancy (bubble = Rent CAGR)**")
            st.altair_chart(c_scatter, use_container_width=True)

# -------- Composite Score (rank bars) --------
with tabs[2]:
    st.subheader("Composite Development Score (Forward-Looking)")
    st.caption(
        "Select a data source and adjust weights. "
        "**City Summary** reflects current market conditions; "
        "**Development Potential** emphasizes projected growth and feasibility."
    )
    df_city = read_csv(FILES["City Summary"])
    df_dev  = read_csv(FILES["Development Potential"])
    if (df_city is None or df_city.empty) and (df_dev is None or df_dev.empty):
        st.info("Upload city CSVs to compute a score.")
    else:
        source = st.radio("Data Source", ["City Summary", "Development Potential"], horizontal=True)
        base = df_dev if (source == "Development Potential" and isinstance(df_dev, pd.DataFrame)) else df_city

        w_noi  = st.slider("Weight: NOI",       0.0, 1.0, 0.40, 0.05)
        w_cagr = st.slider("Weight: Rent CAGR", 0.0, 1.0, 0.30, 0.05)
        w_vac  = st.slider("Weight: Vacancy",   0.0, 1.0, 0.15, 0.05)
        w_exp  = st.slider("Weight: Expenses / Expense Ratio", 0.0, 1.0, 0.15, 0.05)

        scored = development_score(
            base,
            w_noi=w_noi, w_cagr=w_cagr, w_vac=w_vac, w_exp=w_exp,
            noi_col="Avg NOI",
            cagr_col="Avg Rent CAGR",
            vac_col="Avg Vacancy" if "Avg Vacancy" in base.columns else ("Avg Vacancy Rate" if "Avg Vacancy Rate" in base.columns else base.columns[0]),
            expenses_col="Avg Expenses" if "Avg Expenses" in base.columns else None,
            expense_ratio_col="Avg Expense Ratio" if "Avg Expense Ratio" in base.columns else None,
        )
        ranked = scored.sort_values("Development Score", ascending=False)
        show_df(ranked)
        st.download_button("Download Scored Markets CSV", data=ranked.to_csv(index=False), file_name="Market_Scores.csv", use_container_width=True)

        if "City" in ranked.columns:
            c_bars = alt.Chart(ranked).mark_bar().encode(
                x=alt.X("Development Score:Q", title="Composite Score"),
                y=alt.Y("City:N", sort="-x", title=""),
                tooltip=["City", "Development Score", "Avg NOI", "Avg Rent CAGR", "Avg Vacancy"]
            ).properties(height=220)
            st.markdown("**Ranked Markets by Composite Score**")
            st.altair_chart(c_bars, use_container_width=True)
            st.success(f"Top market by current weights: **{ranked.iloc[0]['City']}**")

# -------- New Hope Class B --------
with tabs[3]:
    st.subheader("New Hope – Class B Summary")
    st.caption("Key metrics used to benchmark feasibility for the target development class.")
    df_b = read_csv(FILES["New Hope Class B"])
    if df_b is None or df_b.empty:
        st.info("Upload `New_Hope_Class_B_Analysis.csv` to `/data`.")
    else:
        view = df_b.copy()
        for c in ["Avg Rent CAGR", "Avg Vacancy Rate", "Avg Expense Ratio"]:
            if c in view.columns:
                view[c] = (pd.to_numeric(view[c], errors="coerce")*100).round(2).astype(str) + "%"
        show_df(view)
        st.download_button("Download Class B Summary CSV", data=df_b.to_csv(index=False), file_name="New_Hope_ClassB.csv", use_container_width=True)

# -------- Unit-Mix & Valuation --------
with tabs[4]:
    st.subheader("Unit-Mix & Valuation (New Hope, Class B)")
    st.caption(
        "Explore studio/1BR mixes under unit and floor-area constraints. "
        "Outputs include leased units under market capacity, annual NOI, implied value, and DSCR."
    )
    df_unit = read_csv(FILES["New Hope Unit Rents"])
    if df_unit is None or df_unit.empty:
        st.info("Upload `New_Hope_Class_B_Unit_Data.csv` to `/data`.")
    else:
        r_studio = float(df_unit["Avg Studio Rent"].iloc[0])
        r_1br    = float(df_unit["Avg 1-Bedroom Rent"].iloc[0])
        vac_rate = float(df_unit["Avg Vacancy Rate"].iloc[0])
        exp_ratio = float(df_unit["Avg Expense Ratio"].iloc[0])

        st.caption(
            f"Constraints: {TOTAL_UNITS} units · {TOTAL_SF:,} sf · Studio {SF_STUDIO} sf · "
            f"1BR {SF_1BR} sf · Fixed ${FIXED_COST_YR:,}/yr · Variable "
            f"${VAR_COST_STUDIO_MO}/studio/mo & ${VAR_COST_1BR_MO}/1BR/mo."
        )

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            n_st = st.number_input("Studios", min_value=0, max_value=TOTAL_UNITS, value=55, step=1)
        with c2:
            n_1br = st.number_input("1-Bedrooms", min_value=0, max_value=TOTAL_UNITS, value=30, step=1)
        with c3:
            run_opt = st.button("Recommend Best Mix (Max NOI)")
        with c4:
            st.caption(
                f"Avg Rents → Studio: ${r_studio:,.0f} · 1BR: ${r_1br:,.0f} · "
                f"Vacancy: {vac_rate:.1%} · Expense Ratio: {exp_ratio:.0%}"
            )

        if run_opt:
            n_st, n_1br, _best = optimize_mix(r_studio, r_1br, vac_rate)
            st.info(f"Recommended mix (max NOI within constraints): **{n_st} Studios / {n_1br} 1BR**")

        used_sf = n_st*SF_STUDIO + n_1br*SF_1BR
        if n_st + n_1br != TOTAL_UNITS:
            st.warning(f"Total units must equal {TOTAL_UNITS}. Currently {n_st + n_1br}.")
        if used_sf > TOTAL_SF:
            st.error(f"Floor area exceeded: {used_sf:,} sf > {TOTAL_SF:,} sf")

        # Current-mix metrics
        m = unit_mix_metrics(n_st, n_1br, r_studio, r_1br, vac_rate)
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("Used Floor Area", f"{m['used_sf']:,.0f} sf")
        m2.metric("Leased Studios", f"{m['leased_st']:.1f} (cap {m['cap_st']})")
        m3.metric("Leased 1BRs", f"{m['leased_1b']:.1f} (cap {m['cap_1b']})")
        m4.metric("Annual Revenue", fmt_money(m["revenue"]))
        m5.metric("Operating Expenses", fmt_money(m["opex"]))
        m6.metric("NOI", fmt_money(m["noi"]))

        # Heatmap across feasible mixes
        st.markdown("**NOI Heatmap across feasible unit mixes**")
        heat = []
        for s in range(TOTAL_UNITS+1):
            o = TOTAL_UNITS - s
            if s*SF_STUDIO + o*SF_1BR <= TOTAL_SF:
                mm = unit_mix_metrics(s, o, r_studio, r_1br, vac_rate)
                heat.append({"Studios": s, "OneBeds": o, "NOI": mm["noi"]})
        if heat:
            hd = pd.DataFrame(heat)
            chart = alt.Chart(hd).mark_rect().encode(
                x=alt.X("Studios:O"),
                y=alt.Y("OneBeds:O"),
                color=alt.Color("NOI:Q", title="NOI ($)", scale=alt.Scale(scheme="blues")),
                tooltip=["Studios", "OneBeds", alt.Tooltip("NOI:Q", format=",.0f")]
            ).properties(height=360)
            st.altair_chart(chart, use_container_width=True)
        else:
            st.caption("No feasible mixes under current constraints.")

        # Valuation & DSCR + sensitivity
        st.markdown("**Valuation & DSCR**")
        v1, v2, v3, v4 = st.columns(4)
        with v1:
            cap_rate = st.number_input("Cap Rate", min_value=0.01, max_value=0.20, value=0.055, step=0.005, format="%.3f")
        with v2:
            annual_debt_service = st.number_input("Annual Debt Service ($)", min_value=0.0, value=900_000.0, step=50_000.0, format="%.0f")
        with v3:
            show_val = st.checkbox("Show Implied Value", value=True)
        with v4:
            show_dscr = st.checkbox("Show DSCR", value=True)

        implied_value = (m["noi"] / cap_rate) if cap_rate > 0 else np.nan
        dscr = (m["noi"] / annual_debt_service) if annual_debt_service > 0 else np.nan
        cols = st.columns(2)
        if show_val:
            cols[0].metric("Implied Value", fmt_money(implied_value))
        if show_dscr:
            cols[1].metric("DSCR", f"{dscr:.2f}" if pd.notna(dscr) else "—")

        st.caption("Sensitivity: Implied value vs. cap rate")
        cap_range = pd.DataFrame({"Cap Rate": np.linspace(0.035, 0.085, 21)})
        cap_range["Implied Value"] = cap_range["Cap Rate"].apply(lambda c: m["noi"]/c if c > 0 else np.nan)
        sens = alt.Chart(cap_range).mark_line(point=True).encode(
            x=alt.X("Cap Rate:Q", axis=alt.Axis(format=".1%")),
            y=alt.Y("Implied Value:Q", axis=alt.Axis(format="~s")),
            tooltip=[alt.Tooltip("Cap Rate:Q", format=".2%"), alt.Tooltip("Implied Value:Q", format=",.0f")]
        ).properties(height=300)
        st.altair_chart(sens, use_container_width=True)

        # Table + download
        st.markdown("**Pro-Forma Summary (Annual)**")
        tdf = pd.DataFrame({
            "Metric": ["Revenue", "Operating Expenses", "NOI", "Fixed Costs", "Variable Costs (annual)"],
            "Amount": [m["revenue"], m["opex"], m["noi"], FIXED_COST_YR, m["var_cost"]],
        })
        st.table(tdf.assign(Amount=tdf["Amount"].map(lambda x: f"${x:,.0f}")))
        st.download_button("Download Pro-Forma (Current Mix)", data=tdf.to_csv(index=False), file_name="ProForma_CurrentMix.csv", use_container_width=True)

# -------- Workbook Preview --------
with tabs[5]:
    st.subheader("Workbook Preview")
    st.caption("Quick peek at selected sheets from the supporting Excel model.")
    previews = read_excel_preview(ANALYSIS_XLSX)
    if previews:
        sheet_names = list(previews.keys())
        chosen = st.selectbox("Select a sheet to preview", sheet_names)
        show_df(previews[chosen])
    else:
        st.info("Upload your Excel workbook to `/analysis` to preview sheets.")
