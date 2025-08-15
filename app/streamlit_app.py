from pathlib import Path
import pandas as pd
import numpy as np
import streamlit as st

st.set_page_config(page_title="CRE Market & Development Analysis", layout="wide")

# ---------- Paths ----------
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ANALYSIS = ROOT / "analysis" / "CRE_Data_SpringA2025_Analysis.xlsx"

FILES = {
    "City Summary": DATA / "City_Level_Market_Summary.csv",
    "Development Potential": DATA / "City_Development_Potential.csv",
    "New Hope Pro Forma": DATA / "New_Hope_Class_B_Analysis.csv",
    "New Hope Units": DATA / "New_Hope_Class_B_Unit_Data.csv",
}

# ---------- Loaders ----------
@st.cache_data(show_spinner=False)
def read_csv(p: Path) -> pd.DataFrame | None:
    if p.exists():
        try:
            return pd.read_csv(p)
        except Exception as e:
            st.warning(f"Could not read {p.name}: {e}")
    return None

@st.cache_data(show_spinner=False)
def read_excel_preview(p: Path, nrows=15) -> dict[str, pd.DataFrame]:
    out = {}
    if p.exists():
        try:
            xls = pd.ExcelFile(p)
            for sh in xls.sheet_names:
                try:
                    out[sh] = xls.parse(sh, nrows=nrows)
                except Exception:
                    pass
        except Exception as e:
            st.warning(f"Could not open {p.name}: {e}")
    return out

def pct(x):
    x = pd.to_numeric(x, errors="coerce")
    return (x * 100).round(1).astype("float")

# ---------- Header ----------
st.title("Commercial Real Estate Market & Development Analysis")
st.caption("City KPIs, development scoring, and an 85-unit Class B pro forma (Excel-first).")

# ---------- Tabs ----------
tab_overview, tab_kpis, tab_dev, tab_newhope = st.tabs(
    ["Overview", "Market KPIs", "Development Potential", "New Hope Pro Forma"]
)

# ---------- Overview ----------
with tab_overview:
    st.subheader("Files Detected")
    c1, c2 = st.columns(2)
    with c1:
        for label, path in FILES.items():
            st.write(f"- **{label}:** `{path.name}` — " + ("✅ found" if path.exists() else "❌ missing"))
    with c2:
        st.write(f"- **Excel Model:** `{ANALYSIS.name}` — " + ("✅ found" if ANALYSIS.exists() else "❌ missing"))

    # Executive Summary (auto)
    st.divider()
    st.subheader("Executive Summary")
    city = read_csv(FILES["City Summary"])
    dev = read_csv(FILES["Development Potential"])
    pf = read_csv(FILES["New Hope Pro Forma"])

    summary_lines = []
    if dev is not None and "Score" in dev.columns:
        top_city = dev.sort_values("Score", ascending=False)["City"].iloc[0]
        summary_lines.append(f"**Top development score:** {top_city}")
    if city is not None:
        # Try to pull New Hope’s KPIs
        try:
            nh = city[city["City"].str.lower() == "new hope"].iloc[0]
            rg = nh.get("Avg Rent CAGR", np.nan)
            vac = nh.get("Avg Vacancy", np.nan)
            summary_lines.append(f"**New Hope KPIs:** Rent CAGR ~ {pct(rg)}%, Vacancy ~ {pct(vac)}%")
        except Exception:
            pass
    if pf is not None:
        # Headline metrics from pro forma if present
        head = []
        for k in ["IRR", "NOI Margin", "DSCR", "Cap Rate"]:
            for c in pf.columns:
                if c.lower().startswith(k.lower().replace(" ", "")) or c.lower().startswith(k.lower()):
                    v = pd.to_numeric(pf[c], errors="coerce").dropna()
                    if not v.empty:
                        if k in ["IRR", "NOI Margin", "Cap Rate"]:
                            head.append(f"{k}: {v.iloc[0]:.1%}" if v.iloc[0] <= 1.5 else f"{k}: {v.iloc[0]:.2f}")
                        else:
                            head.append(f"{k}: {v.iloc[0]:.2f}")
                        break
        if head:
            summary_lines.append("**New Hope Pro Forma:** " + " · ".join(head))

    if summary_lines:
        for line in summary_lines:
            st.write("• " + line)
        st.info(
            "We screened markets via NOI, Vacancy, and Rent CAGR. While the scorecard leader differs, "
            "New Hope offered the best **risk-adjusted** profile and the strongest **NOI margin** under our assumptions."
        )
    else:
        st.info("Add CSVs to /data and the Excel model to /analysis to populate the summary.")

    st.divider()
    st.subheader("Workbook Preview")
    previews = read_excel_preview(ANALYSIS)
    if previews:
        for i, (sheet, df) in enumerate(previews.items()):
            st.markdown(f"**Sheet:** {sheet}")
            st.dataframe(df, use_container_width=True)
            if i >= 2:  # show up to 3 sheets
                break
    else:
        st.caption("No Excel preview available.")

# ---------- Market KPIs ----------
with tab_kpis:
    st.subheader("City-level KPIs")
    df = read_csv(FILES["City Summary"])
    if df is None:
        st.info("Upload `City_Level_Market_Summary.csv` to /data.")
    else:
        # Present as readable table (convert rates to %)
        view = df.copy()
        for col in view.columns:
            if "Vacancy" in col or "CAGR" in col:
                view[col] = pct(view[col])
        st.dataframe(view, use_container_width=True)

        # Simple ranking pickers
        left, right = st.columns([2,1])
        with right:
            sort_col = st.selectbox("Sort by", [c for c in view.columns if c != "City"])
        with left:
            st.markdown(f"**Top Cities by {sort_col}**")
            show = view.sort_values(sort_col, ascending=False).head(10)
            st.bar_chart(show.set_index("City")[sort_col])

# ---------- Development Potential ----------
with tab_dev:
    st.subheader("Development Score (Composite)")
    df = read_csv(FILES["Development Potential"])
    if df is None:
        st.info("Upload `City_Development_Potential.csv` to /data.")
    else:
        # Normalize naming
        if "Development Score" not in df.columns and "Score" in df.columns:
            df = df.rename(columns={"Score": "Development Score"})
        st.dataframe(df, use_container_width=True)

        # Chart
        if "Development Score" in df.columns:
            st.markdown("**Top Markets by Development Score**")
            st.bar_chart(df.set_index("City")["Development Score"].sort_values(ascending=False).head(10))

# ---------- New Hope Pro Forma ----------
with tab_newhope:
    st.subheader("New Hope – 85-Unit Class B Pro Forma")
    df = read_csv(FILES["New Hope Pro Forma"])
    if df is None:
        st.info("Upload `New_Hope_Class_B_Analysis.csv` to /data.")
    else:
        # Show helpful columns if present
        prefer = ["NOI","NOI Margin","Operating Expenses","Revenue","IRR","DSCR","Cap Rate","Cash Flow"]
        cols = [c for c in df.columns if any(k.lower().replace(" ", "") in c.lower().replace(" ", "") for k in prefer)]
        show = df[cols] if cols else df
        # rate-like columns to %
        for c in show.columns:
            if any(k in c.lower() for k in ["irr","margin","cap","rate"]):
                show[c] = pd.to_numeric(show[c], errors="coerce")
        st.dataframe(show, use_container_width=True)

        # Download
        st.download_button("Download Pro Forma CSV", data=df.to_csv(index=False), file_name="New_Hope_Pro_Forma.csv")
