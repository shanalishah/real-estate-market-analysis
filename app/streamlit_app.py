# app/streamlit_app.py
from pathlib import Path
import pandas as pd
import numpy as np
import streamlit as st

st.set_page_config(page_title="CRE Market & Development Analysis", layout="wide")

# ---------------- Paths ----------------
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ANALYSIS = ROOT / "analysis" / "CRE_Data_SpringA2025_Analysis.xlsx"

FILES = {
    "City Summary": DATA / "City_Level_Market_Summary.csv",
    "Development Potential": DATA / "City_Development_Potential.csv",
    "New Hope Pro Forma": DATA / "New_Hope_Class_B_Analysis.csv",
    "New Hope Units": DATA / "New_Hope_Class_B_Unit_Data.csv",  # optional
}

# ---------------- Helpers ----------------
@st.cache_data(show_spinner=False)
def read_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        return pd.read_csv(path)
    except Exception:
        try:
            return pd.read_csv(path, encoding="latin1")
        except Exception as e:
            st.warning(f"Could not read {path.name}: {e}")
            return None

@st.cache_data(show_spinner=False)
def read_excel_preview(path: Path, nrows=15) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    if not path.exists():
        return out
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

def to_pct_series(s: pd.Series) -> pd.Series:
    s_num = pd.to_numeric(s, errors="coerce")
    return (s_num * 100.0).round(1)

def fmt_rate(val) -> str:
    try:
        v = float(val)
    except Exception:
        return str(val)
    return f"{v:.1%}" if v <= 1.5 else f"{v:.2f}"

# ---------------- UI: Header ----------------
st.title("Commercial Real Estate Market & Development Analysis")
st.caption("City KPIs, development scoring, and an 85-unit Class B pro forma (Excel-first, read-only).")

# ---------------- Tabs ----------------
tab_overview, tab_kpis, tab_dev, tab_newhope = st.tabs(
    ["Overview", "Market KPIs", "Development Potential", "New Hope Pro Forma"]
)

# ---------------- Overview ----------------
with tab_overview:
    st.subheader("Files Detected")
    c1, c2 = st.columns(2)
    with c1:
        for label, path in FILES.items():
            st.write(f"- **{label}:** `{path.name}` — " + ("✅ found" if path.exists() else "❌ missing"))
    with c2:
        st.write(f"- **Excel Model:** `{ANALYSIS.name}` — " + ("✅ found" if ANALYSIS.exists() else "❌ missing"))

    st.divider()
    st.subheader("Executive Summary")

    city = read_csv(FILES["City Summary"])
    dev = read_csv(FILES["Development Potential"])
    pf = read_csv(FILES["New Hope Pro Forma"])

    bullets: list[str] = []

    # Development score leader
    if dev is not None:
        dev_view = dev.copy()
        if "Development Score" not in dev_view.columns and "Score" in dev_view.columns:
            dev_view = dev_view.rename(columns={"Score": "Development Score"})
        if "City" in dev_view.columns and "Development Score" in dev_view.columns:
            top = dev_view.sort_values("Development Score", ascending=False).iloc[0]
            bullets.append(f"**Highest composite score:** {top['City']} ({top['Development Score']:.1f}).")

    # New Hope KPIs from city summary
    if city is not None:
        try:
            nh = city[city["City"].str.lower() == "new hope"].iloc[0]
            rg = nh.get("Avg Rent CAGR", np.nan)
            vac = nh.get("Avg Vacancy", np.nan)
            bullets.append(f"**New Hope KPIs:** Rent CAGR ≈ {to_pct_series(pd.Series([rg])).iloc[0]}%, "
                           f"Vacancy ≈ {to_pct_series(pd.Series([vac])).iloc[0]}%.")
        except Exception:
            pass

    # Pro forma highlights (if present)
    if pf is not None:
        head = []
        prefer = ["IRR", "NOI Margin", "DSCR", "Cap Rate"]
        for k in prefer:
            cand = [c for c in pf.columns if c.lower().replace(" ", "").startswith(k.lower().replace(" ", ""))]
            if cand:
                ser = pd.to_numeric(pf[cand[0]], errors="coerce").dropna()
                if not ser.empty:
                    head.append(f"{k}: {fmt_rate(ser.iloc[0])}")
        if head:
            bullets.append("**New Hope Pro Forma:** " + " · ".join(head))

    if bullets:
        for b in bullets:
            st.write("• " + b)
        st.info(
            "Markets were screened via NOI, Vacancy, and Rent CAGR. While the scorecard leader may differ, "
            "**New Hope** offered the best risk-adjusted profile and strongest operating margin under our assumptions."
        )
    else:
        st.info("Add CSVs to `/data` and the Excel model to `/analysis` to populate the summary.")

    st.divider()
    st.subheader("Workbook Preview")
    previews = read_excel_preview(ANALYSIS)
    if previews:
        for i, (sheet, df_sh) in enumerate(previews.items()):
            st.markdown(f"**Sheet:** {sheet}")
            st.dataframe(df_sh, use_container_width=True)
            if i >= 2:
                break
    else:
        st.caption("No Excel preview available.")

# ---------------- Market KPIs ----------------
with tab_kpis:
    st.subheader("City-level KPIs")
    df_city = read_csv(FILES["City Summary"])
    if df_city is None:
        st.info("Upload `City_Level_Market_Summary.csv` to `/data`.")
    else:
        view = df_city.copy()
        # Format percentage-like columns for display
        pct_cols = [c for c in view.columns if any(k in c.lower() for k in ["vacancy", "cagr", "margin", "rate"])]
        for c in pct_cols:
            view[c] = to_pct_series(view[c])

        st.dataframe(view, use_container_width=True)

        # Sort/Filter interface
        left, right = st.columns([2, 1])
        with right:
            sort_by = st.selectbox("Sort by", [c for c in view.columns if c != "City"])
        with left:
            st.markdown(f"**Top Cities by {sort_by}**")
            try:
                # Coerce to numeric to sort, fallback if not numeric
                sort_vals = pd.to_numeric(df_city[sort_by], errors="coerce")
                top_idx = sort_vals.sort_values(ascending=False).index[:10]
                chart_df = pd.DataFrame({
                    "City": df_city.loc[top_idx, "City"].values,
                    sort_by: df_city.loc[top_idx, sort_by].values
                })
                # If this looks like a rate, convert to percentage for chart display
                if sort_by in pct_cols:
                    chart_df[sort_by] = chart_df[sort_by] * 100.0
                st.bar_chart(chart_df.set_index("City"))
            except Exception:
                st.caption("Selected column is not numeric; showing table above instead.")

# ---------------- Development Potential ----------------
with tab_dev:
    st.subheader("Development Potential (Composite Score)")
    df_dev = read_csv(FILES["Development Potential"])
    if df_dev is None:
        st.info("Upload `City_Development_Potential.csv` to `/data`.")
    else:
        dev_view = df_dev.copy()
        if "Development Score" not in dev_view.columns and "Score" in dev_view.columns:
            dev_view = dev_view.rename(columns={"Score": "Development Score"})
        st.dataframe(dev_view, use_container_width=True)

        if "City" in dev_view.columns and "Development Score" in dev_view.columns:
            chart_df = dev_view[["City", "Development Score"]].copy()
            chart_df = chart_df.sort_values("Development Score", ascending=False).head(10)
            st.markdown("**Top Markets by Development Score**")
            st.bar_chart(chart_df.set_index("City"))

# ---------------- New Hope Pro Forma ----------------
with tab_newhope:
    st.subheader("New Hope – 85-Unit Class B Pro Forma")
    df_pf = read_csv(FILES["New Hope Pro Forma"])
    if df_pf is None:
        st.info("Upload `New_Hope_Class_B_Analysis.csv` to `/data`.")
    else:
        show = df_pf.copy()
        # Prefer useful columns if present
        prefer = ["NOI", "NOI Margin", "Operating Expenses", "Revenue",
                  "IRR", "DSCR", "Cap Rate", "Cash Flow"]
        keep = [c for c in show.columns if any(k.lower().replace(" ", "") in c.lower().replace(" ", "") for k in prefer)]
        if keep:
            show = show[keep]

        # Format rate-like columns for the table
        for c in show.columns:
            if any(k in c.lower() for k in ["irr", "margin", "cap", "rate"]) or c.lower().endswith("%"):
                show[c] = pd.to_numeric(show[c], errors="coerce").apply(fmt_rate)

        st.dataframe(show, use_container_width=True)

        st.download_button(
            "Download Pro Forma CSV",
            data=df_pf.to_csv(index=False),
            file_name="New_Hope_Pro_Forma.csv",
            mime="text/csv",
            use_container_width=True,
            key="dl_proforma"
        )

st.markdown("---")
st.caption("This dashboard presents the finalized Excel-based analysis. See the repository for slides and the full workbook.")
