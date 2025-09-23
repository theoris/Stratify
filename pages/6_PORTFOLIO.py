# 6_PORTFOLIO.py
import streamlit as st
import pandas as pd
import numpy as np
import json
from pathlib import Path
from datetime import date
import sys
from supabase import create_client

# --- Setup Supabase ---
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Require login
if "email" not in st.session_state:
    st.error("⛔ Please login first (via Google on Home page).")
    st.stop()

if st.session_state.get("role") not in ["trader", "admin"]:
    st.error("⛔ Only Trader can access this page.")
    st.stop()
st.success("✅ Welcome, Trader!")

# Default state
user_email = st.session_state.get("email", None)
user_role = st.session_state.get("role", "guest")

# ---------- Market Loader ----------
MARKET_PATH = Path("data/market_data_option.json")  # change per index (SET50, GF, etc.)

def load_market(path: Path) -> pd.DataFrame:
    try:
        with open(path, "r", encoding="utf-8") as f:
            market_raw = json.load(f)
        df = pd.DataFrame(market_raw)

        # Normalize columns
        df.columns = [c.strip() for c in df.columns]

        # --- Price ---
        if "Last" in df.columns:
            df["LastPrice"] = pd.to_numeric(df["Last"], errors="coerce")
        elif "Close" in df.columns:
            df["LastPrice"] = pd.to_numeric(df["Close"], errors="coerce")
        elif "SettlePrice" in df.columns:
            df["LastPrice"] = pd.to_numeric(df["SettlePrice"], errors="coerce")
        else:
            df["LastPrice"] = np.nan

        # --- Margin ---
        if "IM" not in df.columns:
            df["IM"] = np.nan
        if "MM" not in df.columns:
            df["MM"] = np.nan

        # Ensure numeric
        df["IM"] = pd.to_numeric(df["IM"], errors="coerce")
        df["MM"] = pd.to_numeric(df["MM"], errors="coerce")

        return df

    except Exception as e:
        st.error(f"Cannot read market JSON: {e}")
        return pd.DataFrame(columns=["Series", "LastPrice", "IM", "MM"])

# Load once
df_market = load_market(MARKET_PATH)

# ---------- Portfolio UI ----------
st.set_page_config(page_title="Portfolio Report", layout="wide", page_icon="📋")
st.title("📊 Portfolio Report")

# --- Load strategies from Supabase ---
res = supabase.table("strategies").select("*").eq("email", user_email).execute()
strategies = res.data if res.data else []

if not strategies:
    st.warning("No saved strategies found in database.")
    st.stop()

# Strategy selection
st.sidebar.header("Select strategies")
selected_names = []
for strat in strategies:
    if st.sidebar.checkbox(strat["name"], value=True, key=f"chk_{strat['id']}"):
        selected_names.append(strat["name"])

portfolio_rows = []

for strat in strategies:
    if strat["name"] not in selected_names:
        continue

    content = strat.get("content", {})
    entry_date = content.get("entry_date", "")
    legs = content.get("legs", [])

    st.subheader(f"📌 {strat['name']} (entry {entry_date})")

    detail_rows = []
    for leg in legs:
        s = leg.get("Series")
        qty = leg.get("Qty", 0)
        entry_price = leg.get("TradePrice", 0.0)

        # lookup market
        mrow = df_market[df_market["Series"] == s]
        last_price = mrow["LastPrice"].iloc[0] if not mrow.empty else np.nan
        im = mrow["IM"].iloc[0] if not mrow.empty else np.nan
        mm = mrow["MM"].iloc[0] if not mrow.empty else np.nan

        # P/L
        pl = (last_price - entry_price) * qty if not pd.isna(last_price) else np.nan

        row = {
            "Series": s,
            "Entry": entry_price,
            "Last": last_price,
            "Qty": qty,
            "P/L": pl,
            "IM": im,
            "MM": mm,
            "Entry Date": entry_date,
        }
        detail_rows.append(row)
        portfolio_rows.append(row)

    df_detail = pd.DataFrame(detail_rows)
    st.dataframe(df_detail)

    # --- Per-strategy totals ---
    if not df_detail.empty:
        st.write(f"**Net P/L (strategy):** {df_detail['P/L'].sum():,.2f}")
        st.write(f"**Total IM (strategy):** {df_detail['IM'].sum():,.2f}")
        st.write(f"**Total MM (strategy):** {df_detail['MM'].sum():,.2f}")
        st.divider()

# ---- Overall Summary ----
if portfolio_rows:
    df_all = pd.DataFrame(portfolio_rows)
    st.subheader("📑 Portfolio Summary")
    st.dataframe(df_all.groupby("Series")[["Qty", "P/L", "IM", "MM"]].sum())
    st.write(f"**Total P/L (portfolio):** {df_all['P/L'].sum():,.2f}")
    st.write(f"**Total IM (portfolio):** {df_all['IM'].sum():,.2f}")
    st.write(f"**Total MM (portfolio):** {df_all['MM'].sum():,.2f}")

if not st.session_state.get("email") or not st.session_state.get("role"):
    st.sidebar.warning("⚠️ Please log in first for more advanced detail.")
else:
    st.sidebar.write(f"Welcome {st.session_state.get('email')} ({st.session_state.get('role')})")

# Sidebar button to go Home
if st.sidebar.button("🏠 Back to HOME"):
    st.switch_page("HOME.py")
