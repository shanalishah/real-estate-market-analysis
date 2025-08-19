# app/streamlit_app.py
from __future__ import annotations
from pathlib import Path
from typing import Dict, Tuple, Optional

import numpy as np
import pandas as pd
import streamlit as st

# ------------------ Page Setup ------------------
st.set_page_config(
    page_title="CRE Market & Development Analysis",
    layout="wide",
)

st.title("Commercial Real Estate Market & Development Analysis")
st.caption("City KPI screening, development scoring, and an 85-unit Class B pro forma — Excel-first, read-only showcase.")

# ------------------ Paths ------------------
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ANALYSIS_XLSX = ROOT / "analysis" / "CRE_Data_SpringA2025_Analysis.xlsx"

FILES: Dict[str, Path] = {
    "City Summary": DATA / "City_Level_Market_Summary.csv",
    "Development Potential": DATA / "City_Development_Potential.csv",
    "New Hope Pro Forma": DATA / "New_Hope_Class_B_Analysis.csv",
}

NEW_HOPE_NAME = "new hope"  # lowercase for matching

# ------------------ Utils ------------------
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
def read_excel_preview(path: Path, nrows: int = 15) -> Dict[str, pd.DataFrame]:
    out: Dict[str, pd.DataFrame] = {}
    if not path.exists():
        return out
    try:
        xls = pd.ExcelFile(path)
        for sh in xls.sheet_names:
            try:
                out[sh] = xls.parse(sh, nrows=nrows)
            except Exception:
                pass
    except Exception:
        pass
    return out

def find_col(df: pd.DataFrame, candidates: Tuple[str, ...]) -> Optional[str]:
    cols = list(df.columns)
    # exact (case-insensitive)
    for c in candidates:
        for col in cols:
            if col.lower().strip() == c.lower().strip():
                return col
    # contains (case-insensitive, ignore spaces)
    def norm(s: str) -> str: return s.lower().replace(" ", "")
    ncands = [norm(c) for c in candidates]
    for col in cols:
        ncol = norm(col)
        if any(c in ncol for c in ncands):
            return col
    return None

def to_pct_series(x: pd.Series) -> pd.Series:
    y = pd.to_numeric(x, errors="coerce")
    return (y * 100.0).round(1)

def fmt_rate(val) -> str:
    try:
        v = float(val)
    except Exception:
        return str(val)
    return f"{v:.1%}" if v <= 1.5 else f"{v:.2f}"

def safe_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")

# ------------------ Tabs ------------------
tab_overview, tab_kpis, tab_dev, tab_newhope, tab_scenario, tab_workbook = st.tabs(
    ["Overview", "Market KPIs", "Development Score", "New Hope Pro Forma", "Scenario Sandbox", "Workbook Trace"]
)

# ------------------ Overview ------------------
with tab_overview:
    st.subheader("Files Detected")
    c1, c2 = st.columns(2)
    with c1:
        for label, path in FILES.items():
            st.write(f"- **{label}:** `{path.name}` — " + ("✅ found" if path.exists() else "❌ missing"))
    with c2:
        st.write(f"- **Excel Model:** `{ANALYSIS_XLSX.name}` — " + ("✅ found" if ANALYSIS_XLSX.exists() else "❌ missing"))

    st.divider()
    st.subheader("Executive Summary")

    df_city = read_csv(FILES["City Summary"])
    df_dev = read_csv(FILES["Development Potential"])
    df_pf = read_csv(FILES["New Hope Pro Forma"])

    bullets = []

    # 1) Top development score city
    if isinstance(df_dev, pd.DataFrame) and not df_dev.empty:
        # standardize score column
        score_col = find_col(df_dev, ("Development Score", "Score"))
        city_col = find_col(df_dev, ("City", "Market", "MSA"))
        if score_col and city_col:
            dev_sorted = df_dev.sort_values(score_col, ascending=False)
            top_row = dev_sorted.iloc[0]
            bullets.append(f"**Highest composite development score:** {top_row[city_col]} ({top_row[score_col]:.1f}).")

    # 2) New Hope KPIs
    if isinstance(df_city, pd.DataFrame) and not df_city.empty:
        c_city = find_col(df_city, ("City", "Market", "MSA"))
        c_cagr = find_col(df_city, ("Avg Rent CAGR", "Rent CAGR"))
        c_vac = find_col(df_city, ("Avg Vacancy", "Vacancy"))
        if c_city:
            mask_nh = df_city[c_city].astype(str).str.lower().eq(NEW_HOPE_NAME)
            if mask_nh.any():
                nh = df_city.loc[mask_nh].iloc[0]
                parts = []
                if c_cagr:
                    parts.append(f"Rent CAGR ≈ {to_pct_series(pd.Series([nh[c_cagr]])).iloc[0]}%")
                if c_vac:
                    parts.append(f"Vacancy ≈ {to_pct_series(pd.Series([nh[c_vac]])).iloc[0]}%")
                if parts:
                    bullets.append("**New Hope KPIs:** " + " · ".join(parts) + ".")

    # 3) Pro forma highlights (IRR, NOI Margin, DSCR, Cap Rate)
    if isinstance(df_pf, pd.DataFrame) and not df_pf.empty:
        highlight_keys = ("IRR", "NOI Margin", "DSCR", "Cap Rate")
        head = []
        for k in highlight_keys:
            col = find_col(df_pf, (k,))
            if col is not None:
                ser = safe_num(df_pf[col]).dropna()
                if not ser.empty:
                    head.append(f"{k}: {fmt_rate(ser.iloc[0])}")
        if head:
            bullets.append("**New Hope pro forma:** " + " · ".join(head) + ".")

    if bullets:
        for b in bullets:
            st.write("• " + b)
        st.info(
            "Markets were screened via NOI, Vacancy, and Rent CAGR. While the scorecard leader can differ, "
            "**New Hope** offered the most balanced, risk-adjusted profile and strong operating margin under our assumptions."
        )
    else:
        st.info("Add CSVs to `/data` and the Excel workbook to `/analysis` to populate the summary.")

# ------------------ Market KPIs ------------------
with tab_kpis:
    st.subheader("City-level KPIs")
    df = read_csv(FILES["City Summary"])
    if df is None or df.empty:
        st.info("Upload `City_Level_Market_Summary.csv` to `/data`.")
    else:
        df_view = df.copy()
        # Convert known rate columns to % for display
        for col in df_view.columns:
            if any(k in col.lower() for k in ["vacancy", "cagr", "margin", "rate", "%"]):
                df_view[col] = to_pct_series(df_view[col])
        st.dataframe(df_view, use_container_width=True)

        # Simple explorer
        c_city = find_col(df_view, ("City", "Market", "MSA")) or df_view.columns[0]
        kpi_choices = [c for c in df_view.columns if c != c_city]
        left, right = st.columns([2, 1])
        with right:
            sort_kpi = st.selectbox("Sort by KPI", kpi_choices, index=min(1, len(kpi_choices)-1))
        with left:
            st.markdown(f"**Top markets by {sort_kpi}**")
            numeric = safe_num(df[sort_kpi])
            top = df.loc[numeric.sort_values(ascending=False).head(10).index, [c_city, sort_kpi]].copy()
            # If rate-like, scale to % for chart
            is_rate = any(k in sort_kpi.lower() for k in ["vacancy", "cagr", "margin", "rate", "%"])
            if is_rate:
                top[sort_kpi] = top[sort_kpi] * 100.0
            st.bar_chart(top.set_index(c_city))

# ------------------ Development Score ------------------
with tab_dev:
    st.subheader("Development Potential (Composite Score)")
    df = read_csv(FILES["Development Potential"])
    if df is None or df.empty:
        st.info("Upload `City_Development_Potential.csv` to `/data`.")
    else:
        score_col = find_col(df, ("Development Score", "Score"))
        c_city = find_col(df, ("City", "Market", "MSA")) or df.columns[0]
        if score_col and c_city:
            df_view = df.rename(columns={score_col: "Development Score"})
            st.dataframe(df_view, use_container_width=True)
            st.markdown("**Top markets by Development Score**")
            top = df_view.sort_values("Development Score", ascending=False).head(10)
            st.bar_chart(top.set_index(c_city)["Development Score"])
        else:
            st.dataframe(df, use_container_width=True)
            st.caption("Could not find a `Score`/`Development Score` column to chart.")

# ------------------ New Hope Pro Forma ------------------
with tab_newhope:
    st.subheader("New Hope — 85-Unit Class B Pro Forma")
    df = read_csv(FILES["New Hope Pro Forma"])
    if df is None or df.empty:
        st.info("Upload `New_Hope_Class_B_Analysis.csv` to `/data`.")
    else:
        show = df.copy()
        # Prefer helpful columns if they exist
        prefer = ("NOI", "NOI Margin", "Operating Expenses", "Revenue", "IRR", "DSCR", "Cap Rate", "Cash Flow", "Debt Service")
        keep = [c for c in show.columns if any(k.lower().replace(" ", "") in c.lower().replace(" ", "") for k in prefer)]
        show = show[keep] if keep else show

        # Format rate-like columns for readability
        for c in show.columns:
            if any(k in c.lower() for k in ["irr", "margin", "cap", "rate", "%"]):
                show[c] = safe_num(show[c]).apply(fmt_rate)
        st.dataframe(show, use_container_width=True)

        st.download_button(
            "Download Pro Forma CSV",
            data=df.to_csv(index=False),
            file_name="New_Hope_Pro_Forma.csv",
            mime="text/csv",
            use_container_width=True,
            key="dl_pf"
        )

# ------------------ Scenario Sandbox ------------------
with tab_scenario:
    st.subheader("Scenario Sandbox (read-only approximation)")
    st.caption(
        "Adjust high-level shocks to see directional impacts. "
        "Calculations use the pro forma’s first row if available."
    )
    df = read_csv(FILES["New Hope Pro Forma"])
    if df is None or df.empty:
        st.info("Upload `New_Hope_Class_B_Analysis.csv` to `/data`.")
    else:
        # Find baseline columns
        col_rev = find_col(df, ("Revenue", "Total Revenue", "Gross Revenue"))
        col_opex = find_col(df, ("Operating Expenses", "Opex"))
        col_noi = find_col(df, ("NOI",))
        col_debt = find_col(df, ("Debt Service", "Annual Debt Service"))
        col_cap = find_col(df, ("Cap Rate", "CapRate"))

        if not any([col_rev, col_opex, col_noi]):
            st.warning("Could not find Revenue/Operating Expenses/NOI columns to run a scenario.")
        else:
            base = df.iloc[0].copy()
            base_rev = float(base[col_rev]) if col_rev else (float(base[col_noi]) + float(base[col_opex]))
            base_opex = float(base[col_opex]) if col_opex else max(base_rev - float(base[col_noi]), 0.0)
            base_noi = float(base[col_noi]) if col_noi else (base_rev - base_opex)
            base_debt = float(base[col_debt]) if col_debt else np.nan
            base_cap = float(base[col_cap]) if col_cap else np.nan
            base_margin = base_noi / base_rev if base_rev else np.nan
            base_value = (base_noi / base_cap) if (col_cap and base_cap and base_cap > 0) else np.nan
            base_dscr = (base_noi / base_debt) if (col_debt and base_debt and base_debt > 0) else np.nan

            c1, c2, c3 = st.columns(3)
            with c1:
                rev_shock = st.slider("Revenue change", -0.15, 0.15, 0.00, 0.01, format="%.0f%%")
            with c2:
                opex_shock = st.slider("Opex change", -0.15, 0.15, 0.00, 0.01, format="%.0f%%")
            with c3:
                cap_shock = st.slider("Cap rate change (bps)", -200, 200, 0, 25)

            # Scenario calcs
            scen_rev = base_rev * (1 + rev_shock)
            scen_opex = base_opex * (1 + opex_shock)
            scen_noi = scen_rev - scen_opex
            scen_margin = scen_noi / scen_rev if scen_rev else np.nan
            scen_cap = (base_cap + cap_shock / 10000.0) if col_cap else np.nan
            scen_value = (scen_noi / scen_cap) if (col_cap and scen_cap and scen_cap > 0) else np.nan
            scen_dscr = (scen_noi / base_debt) if (col_debt and base_debt and base_debt > 0) else np.nan

            st.markdown("**Baseline vs Scenario**")
            mcols = st.columns(6)
            labels_vals = [
                ("NOI Margin", base_margin, scen_margin, True),
                ("NOI ($)", base_noi, scen_noi, False),
                ("Revenue ($)", base_rev, scen_rev, False),
                ("Opex ($)", base_opex, scen_opex, False),
                ("Cap Rate", base_cap, scen_cap, True),
                ("DSCR", base_dscr, scen_dscr, False),
            ]
            for (label, b, s, is_rate), col in zip(labels_vals, mcols):
                with col:
                    b_txt = fmt_rate(b) if is_rate else (f"${b:,.0f}" if pd.notna(b) else "—")
                    s_txt = fmt_rate(s) if is_rate else (f"${s:,.0f}" if pd.notna(s) else "—")
                    st.metric(label=label, value=s_txt, delta=(f"vs {b_txt}"))

            if pd.notna(scen_value):
                st.caption(f"Implied Value (NOI / Cap Rate): **${scen_value:,.0f}**")

# ------------------ Workbook Trace ------------------
with tab_workbook:
    st.subheader("Workbook Trace (Preview)")
    previews = read_excel_preview(ANALYSIS_XLSX)
    if previews:
        for i, (sheet, df_sh) in enumerate(previews.items()):
            st.markdown(f"**Sheet:** {sheet}")
            st.dataframe(df_sh, use_container_width=True)
            if i >= 3:  # show up to 4 sheets
                break
    else:
        st.info("Upload your Excel analysis file to `/analysis` to preview sheets.")
