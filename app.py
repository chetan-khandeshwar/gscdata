# app.py
import streamlit as st
import datetime
import pandas as pd
import os
import math

from gsc_weekly_report import generate_report

st.set_page_config(page_title="GSC Weekly Report All Sites", layout="wide")
st.title("📊 GSC Weekly Report All Sites")

st.markdown(
    "This app runs the GSC multi-site summary automatically. "
    "(Last 7 Days Selected by Default)"
)

# --- Custom CSS for buttons ---
st.markdown("""
    <style>
    div[data-testid="stButton"] > button:first-child {
        border-radius: 8px;
        height: 3em;
        min-width: 120px;
        font-weight: 600;
        color: white;
    }
    /* First button (28 Days) */
    div[data-testid="stButton"]:nth-of-type(1) > button {
        background-color: #007bff; /* blue */
    }
    /* Second button (90 Days) */
    div[data-testid="stButton"]:nth-of-type(2) > button {
        background-color: #007bff; /* blue */
    }
    /* Third button (Generate Report) */
    div[data-testid="stButton"]:nth-of-type(3) > button {
        background-color: #ff6b6b; /* light red */
        color: white;
    }
    /* Small tweak: make download button appear normal */
    div[data-testid="stDownloadButton"] > button {
        background-color: white;
        color: inherit;
        border-radius: 6px;
    }
    </style>
""", unsafe_allow_html=True)

# --- date session state defaults (use separate names so we can update safely) ---
today = datetime.date.today()
if "range_start" not in st.session_state:
    st.session_state["range_start"] = today - datetime.timedelta(days=7)
if "range_end" not in st.session_state:
    st.session_state["range_end"] = today

# Callback that updates the session vars (no explicit rerun)
def set_last_n_days_cb(n):
    st.session_state["range_start"] = today - datetime.timedelta(days=(n - 1))
    st.session_state["range_end"] = today
    # NOTE: no explicit st.experimental_rerun() — Streamlit will rerun after the callback.

# Render date inputs using the *values* from session_state (no conflicting widget key)
col_left, col_right = st.columns([3, 2])
with col_left:
    start_date = st.date_input("Start date", value=st.session_state["range_start"])
with col_right:
    end_date = st.date_input("End date", value=st.session_state["range_end"])

# Keep session_state in sync if user manually edits the widgets
st.session_state["range_start"] = start_date
st.session_state["range_end"] = end_date

# Quick range buttons row (28 Days & 90 Days) — use on_click callbacks
b1, b2, spacer = st.columns([1,1,6])
with b1:
    st.button("28 Days", on_click=set_last_n_days_cb, args=(28,))
with b2:
    st.button("90 Days", on_click=set_last_n_days_cb, args=(90,))

st.markdown("")  # spacing

# Always auto-detect client_secret.json
candidate = os.path.join(os.getcwd(), "client_secret.json")
creds_path = candidate if os.path.exists(candidate) else None

row_limit = st.number_input("Row limit per query", min_value=1000, max_value=25000, value=25000, step=1000)
st.markdown("")

# Helper functions
def period_previous(start, end):
    length_days = (end - start).days + 1
    prev_end = start - datetime.timedelta(days=1)
    prev_start = prev_end - datetime.timedelta(days=length_days - 1)
    return prev_start, prev_end

def agg_metrics(df):
    if df is None or df.empty:
        return {"clicks": 0, "impressions": 0, "ctr": 0.0, "position": float("nan")}
    clicks = df["clicks"].sum() if "clicks" in df.columns else 0
    impressions = df["impressions"].sum() if "impressions" in df.columns else 0
    ctr = (clicks / impressions) if impressions else 0.0
    if "position" in df.columns and impressions:
        weighted_pos = (df["position"].fillna(0) * df.get("impressions", pd.Series(0))).sum() / impressions
    elif "position" in df.columns:
        weighted_pos = df["position"].mean()
    else:
        weighted_pos = float("nan")
    return {"clicks": int(clicks), "impressions": int(impressions), "ctr": float(ctr), "position": float(weighted_pos)}

def pct_change(curr, prev):
    try:
        if prev == 0 or prev is None:
            return None
        return (curr - prev) / prev
    except Exception:
        return None

def format_pct(x):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return ""
    return f"{x * 100:.2f}%"

def format_num(x):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return ""
    if isinstance(x, int) or (isinstance(x, float) and x.is_integer()):
        return f"{int(x):,}"
    return f"{x:.2f}"

# Main: always use sites.txt
if st.button("Generate Report"):
    # use the start/end currently in session_state (keeps behavior consistent)
    start_date = st.session_state["range_start"]
    end_date = st.session_state["range_end"]

    if start_date > end_date:
        st.error("Start date must be on or before end date.")
    else:
        with st.spinner("Fetching site summaries from Google Search Console..."):
            prev_start, prev_end = period_previous(start_date, end_date)
            sites_file = os.path.join(os.getcwd(), "sites.txt")
            if not os.path.exists(sites_file):
                st.error(f"sites.txt not found in project folder. Create {sites_file} with one site URL per line.")
                st.stop()

            with open(sites_file, "r", encoding="utf-8") as fh:
                sites = [line.strip() for line in fh if line.strip()]

            if not sites:
                st.error("sites.txt is empty. Add one property URL per line.")
                st.stop()

            results = []
            for site in sites:
                try:
                    df_curr = generate_report(start_date, end_date, property_url=site, credentials_path=creds_path, row_limit=row_limit)
                    df_prev = generate_report(prev_start, prev_end, property_url=site, credentials_path=creds_path, row_limit=row_limit)
                except Exception as e:
                    err_text = str(e)
                    if "403" in err_text or "not authorized" in err_text.lower():
                        msg = "Not authorized"
                    elif "not found" in err_text.lower() or "404" in err_text:
                        msg = "Property not found"
                    elif "No credentials_path" in err_text or "No credentials" in err_text:
                        msg = "No credentials"
                    else:
                        msg = "Error"
                    results.append({
                        "Site": site,
                        "Clicks (Current)": None,
                        "Clicks (Prev)": None,
                        "Clicks %": msg,
                        "Impr (Current)": None,
                        "Impr (Prev)": None,
                        "Impr %": msg,
                        "CTR (Current)": None,
                        "CTR (Prev)": None,
                        "CTR %": msg,
                        "Avg Position (Current)": None,
                        "Avg Position (Prev)": None,
                        "Position %": msg
                    })
                    continue

                agg_c = agg_metrics(df_curr)
                agg_p = agg_metrics(df_prev)

                clicks_pct = pct_change(agg_c["clicks"], agg_p["clicks"]) if agg_p["clicks"] else None
                impr_pct = pct_change(agg_c["impressions"], agg_p["impressions"]) if agg_p["impressions"] else None
                ctr_pct = pct_change(agg_c["ctr"], agg_p["ctr"]) if agg_p["impressions"] else None
                pos_pct = pct_change(agg_c["position"], agg_p["position"]) if (not math.isnan(agg_c["position"]) and not math.isnan(agg_p["position"]) and agg_p["position"] != 0) else None

                results.append({
                    "Site": site,
                    "Clicks (Current)": agg_c["clicks"],
                    "Clicks (Prev)": agg_p["clicks"],
                    "Clicks %": format_pct(clicks_pct),
                    "Impr (Current)": agg_c["impressions"],
                    "Impr (Prev)": agg_p["impressions"],
                    "Impr %": format_pct(impr_pct),
                    "CTR (Current)": format_pct(agg_c["ctr"]),
                    "CTR (Prev)": format_pct(agg_p["ctr"]),
                    "CTR %": format_pct(ctr_pct),
                    "Avg Position (Current)": f"{agg_c['position']:.2f}" if not math.isnan(agg_c["position"]) else "",
                    "Avg Position (Prev)": f"{agg_p['position']:.2f}" if not math.isnan(agg_p["position"]) else "",
                    "Position %": format_pct(pos_pct)
                })

            out_df = pd.DataFrame(results)
            st.success("Report generated ✅")
            st.dataframe(out_df)
            csv = out_df.to_csv(index=False).encode("utf-8")
            st.download_button("⬇️ Download CSV", data=csv, file_name="gsc_sites_summary_auto_creds.csv", mime="text/csv")
