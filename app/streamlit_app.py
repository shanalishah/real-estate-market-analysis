
from pathlib import Path
import pandas as pd
import numpy as np
import streamlit as st

st.set_page_config(page_title="CRE Market & Development Analysis", layout="wide")

# -------- Paths --------
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ANALYSIS_XLSX = (ROOT / "analysis" / "CRE_Data_SpringA2025_Analysis.xlsx")

FILES = {
    "City Summary": DATA / "City_Level_Market_Summary.csv",
    "Development Potential": DATA / "City_Development_Potential.csv",
    "New Hope Pro Forma": DATA / "New_Hope_Class_B_Analysis.csv",
}

# -------- Loaders --------
@st.cache_data(show_spinner=False)
def read_csv(path: Path) -> pd.DataFrame | None:
    if path.exists():
        try:
            return pd.read_csv(path)
        except Exception as e:
            st.warning(f"Could not read {path.name}: {e}")
    return None

@st.cache_data(show_spinner=False)
def read_excel_preview(path: Path, nrows=20) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    if path.exists():
        try:
            xls = pd.ExcelFile(path)
            for sh in xls.sheet_names:
                try:
                    out[sh] = xls.parse(sh, nrows=nrows)
                except Exception:
                    pass
        except Exception as e:
            st.warning(f"Could not open {path.name}: {e}")
    return out

# -------- UI: Header --------
st.title("Commercial Real Estate Market & Development Analysis")
st.caption("City KPIs, development potential, and an 85-unit Class B pro forma (read-only showcase).")

# -------- Tabs --------
tab_overview, tab_kpis, tab_dev, tab_newhope = st.tabs(
    ["Overview", "Market KPIs", "Development Potential", "New Hope Pro Forma"]
)

# -------- Overview --------
with tab_overview:
    st.subheader("Project Files")
    c1, c2 = st.columns(2)
    with c1:
        for label, path in FILES.items():
            st.write(f"- **{label}:** `{path.name}` — " + ("✅ found" if path.exists() else "❌ missing"))
    with c2:
        x_ok = ANALYSIS_XLSX.exists()
        st.write(f"- **Workbook:** `{ANALYSIS_XLSX.name}` — " + ("✅ found" if x_ok else "❌ missing"))

    st.divider()
    st.subheader("Workbook Preview")
    previews = read_excel_preview(ANALYSIS_XLSX)
    if previews:
        # Show up to 3 sheets
        for i, (sheet, df) in enumerate(previews.items()):
            st.markdown(f"**Sheet:** {sheet}")
            st.dataframe(df, use_container_width=True)
            if i >= 2:
                break
    else:
        st.info("No Excel preview available (file missing or unreadable).")

# -------- Market KPIs --------
with tab_kpis:
    st.subheader("City-level KPIs")
    df_city = read_csv(FILES["City Summary"])
    if df_city is None:
        st.info("`City_Level_Market_Summary.csv` not found in /data.")
    else:
        # Identify likely city column
        norm = {c.lower(): c for c in df_city.columns}
        city_col = norm.get("city") or norm.get("market") or df_city.columns[0]

        # Pick a KPI to sort
        kpi_options = [c for c in df_city.columns if c != city_col]
        default_idx = 0 if not kpi_options else min(1, len(kpi_options)-1)

        left, right = st.columns([2,1])
        with left:
            cities = sorted(df_city[city_col].dropna().unique().tolist())
            pick = st.multiselect("Filter markets (optional)", cities, default=cities[:8])
        with right:
            kpi = st.selectbox("Sort by KPI", kpi_options, index=default_idx)

        df_view = df_city.copy()
        if pick:
            df_view = df_view[df_view[city_col].isin(pick)]
        # Ensure numeric for sort; fallback safe
        if pd.api.types.is_numeric_dtype(df_view[kpi]):
            df_view = df_view.sort_values(by=kpi, ascending=False)
        st.dataframe(df_view, use_container_width=True)

        # Top 10 bar chart if numeric
        if pd.api.types.is_numeric_dtype(df_view[kpi]):
            st.markdown(f"**Top 10 by {kpi}**")
            st.bar_chart(df_view[[city_col, kpi]].set_index(city_col).head(10))

# -------- Development Potential --------
with tab_dev:
    st.subheader("Development Potential by City")
    df_dev = read_csv(FILES["Development Potential"])
    if df_dev is None:
        st.info("`City_Development_Potential.csv` not found in /data.")
    else:
        st.dataframe(df_dev, use_container_width=True)

        # find a likely score column to chart
        score_col = None
        for cand in ["score","development_score","rank","composite_score","index"]:
            for c in df_dev.columns:
                if c.lower() == cand:
                    score_col = c
                    break
            if score_col: break

        if score_col:
            name_col_candidates = [c for c in df_dev.columns if c.lower() in {"city","market","msa"}]
            name_col = name_col_candidates[0] if name_col_candidates else df_dev.columns[0]
            top = df_dev.sort_values(by=score_col, ascending=False).head(10)
            st.markdown(f"**Top Markets by `{score_col}`**")
            st.bar_chart(top.set_index(name_col)[score_col])

# -------- New Hope Pro Forma --------
with tab_newhope:
    st.subheader("New Hope – 85-Unit Class B Pro Forma")
    df_pf = read_csv(FILES["New Hope Pro Forma"])

    if df_pf is None:
        st.info("`New_Hope_Class_B_Analysis.csv` not found in /data.")
    else:
        # Show helpful columns if present
        keep_like = ["NOI","NOI Margin","Operating Expenses","Cap Rate","IRR","NPV",
                     "DSCR","Debt Service","Revenue","Rent","Cash Flow"]
        show_cols = [c for c in df_pf.columns if any(k.lower() in c.lower() for k in keep_like)]
        st.dataframe(df_pf[show_cols] if show_cols else df_pf, use_container_width=True)

        # Small KPI cards (if present)
        kpi_cards = {}
        for k in ["IRR","NOI Margin","DSCR","Cap Rate"]:
            for c in df_pf.columns:
                if c.lower().startswith(k.lower()):
                    # take first non-null numeric value as a summary
                    s = pd.to_numeric(df_pf[c], errors="coerce").dropna()
                    if not s.empty:
                        kpi_cards[k] = s.iloc[0]
                        break

        if kpi_cards:
            st.markdown("**Headline KPIs (from pro forma):**")
            cols = st.columns(len(kpi_cards))
            for (k, v), col in zip(kpi_cards.items(), cols):
                with col:
                    if isinstance(v, (int, float)) and not pd.isna(v):
                        if "rate" in k.lower() or "irr" in k.lower() or "margin" in k.lower():
                            col.metric(k, f"{v:,.2%}" if v <= 1.0 else f"{v:,.2f}")
                        else:
                            col.metric(k, f"{v:,.2f}")
                    else:
                        col.metric(k, str(v))

        st.download_button(
            "Download Pro Forma CSV",
            data=df_pf.to_csv(index=False),
            file_name="New_Hope_Pro_Forma.csv",
            mime="text/csv",
            use_container_width=True
        )

st.markdown("---")
st.caption("Read-only showcase of KPIs, development scoring, and the New Hope pro forma.")
