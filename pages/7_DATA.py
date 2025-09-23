# options_app.py
import json
import re
import calendar
from pathlib import Path
from datetime import date
import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import norm
import itertools
import sys
# Add parent directory (app/) to Python path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from auth import verify_user, add_user, current_user, role_required,get_user_role

# Require login
if "email" not in st.session_state:
    st.error("⛔ Please login first (via Google on Home page).")
    st.stop()

if st.session_state.get("role") not in ["trader", "admin"]:
    st.error("⛔ Only Trader can access this page.")
    st.stop()
st.success("✅ Welcome, Trader!")

SAVE_DIR = Path("saved_strategies")
SAVE_DIR.mkdir(exist_ok=True)
# ------------------- Helpers -------------------
def parse_num(x):
    if x is None: return np.nan
    if isinstance(x,(int,float)): return float(x)
    if isinstance(x,str):
        s = x.strip().replace(',','')
        if s in ['','-','NA','NaN','--']: return np.nan
        try: return float(s)
        except: return np.nan
    return np.nan

def leg_type_from_series(series):
    if not isinstance(series,str): return (None, np.nan)
    if 'C' in series:
        idx = series.rfind('C'); opt = 'Call'
    elif 'P' in series:
        idx = series.rfind('P'); opt = 'Put'
    else:
        return (None, np.nan)
    strike_part = series[idx+1:]
    try:
        strike = float(strike_part)
    except:
        digits = ''.join(ch for ch in series if ch.isdigit())
        strike = float(digits) if digits else np.nan
    return (opt, strike)

def choose_price_from_row(row):
    last = parse_num(row.get('Last')) if isinstance(row, dict) else parse_num(row.Last)
    bid = parse_num(row.get('Bid')) if isinstance(row, dict) else parse_num(getattr(row, "Bid", None))
    offer = parse_num(row.get('Offer')) if isinstance(row, dict) else parse_num(getattr(row, "Offer", None))
    if not np.isnan(last): return last
    if not np.isnan(bid) and not np.isnan(offer): return (bid + offer) / 2.0
    if not np.isnan(bid): return bid
    if not np.isnan(offer): return offer
    return np.nan

def payoff_for_leg_intrinsic(opt_type, K, qty, premium, multiplier, S_arr):
    if opt_type == 'Call':
        intrinsic = np.maximum(S_arr - K, 0.0)
    elif opt_type == 'Put':
        intrinsic = np.maximum(K - S_arr, 0.0)
    else:  # Future
        intrinsic = S_arr
    return (intrinsic - premium) * qty * multiplier

def bs_price(opt_type, S, K, T, rf, sigma):
    if T <= 0 or sigma <= 0 or np.isnan(sigma):
        return max(S - K, 0.0) if opt_type == 'Call' else max(K - S, 0.0)
    d1 = (np.log(S / K) + (rf + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if opt_type == 'Call':
        return S * norm.cdf(d1) - K * np.exp(-rf * T) * norm.cdf(d2)
    else:
        return K * np.exp(-rf * T) * norm.cdf(-d2) - S * norm.cdf(-d1)

def payoff_for_leg_bs(opt_type, K, qty, premium, multiplier, S_arr, T, rf, sigma):
    prices = np.array([bs_price(opt_type, s, K, T, rf, sigma) for s in S_arr])
    return (prices - premium) * qty * multiplier

# expiry parsing (month letter + 2-digit year)
EXPIRY_ORDER = "FGHJKMNQUVXZ"
MONTH_MAP = {"F":1,"G":2,"H":3,"J":4,"K":5,"M":6,"N":7,"Q":8,"U":9,"V":10,"X":11,"Z":12}
def parse_expiry_code(series):
    if not isinstance(series,str): return (None, np.nan, None)
    if len(series) <= 7:
        #future
        letter = series[-3]
        year2 = series[-2:]
    else:
        #option series
        clean_series = series[:-4]
        letter = clean_series[-3]
        year2 = clean_series[-2:]
    # m = re.search(r'([FGHJKMNQUVXZ])(\d{2})', series)
    # if not m: return (None, np.nan, None)
    # letter, year2 = m.group(1), m.group(2)
    month = MONTH_MAP.get(letter, 1)
    year = 2000 + int(year2)
    cal = calendar.Calendar(firstweekday=0)
    fridays = [d for d in cal.itermonthdates(year, month) if d.month == month and d.weekday() == 4]
    # pick 3rd Friday if present else fallback to middle of month
    expiry_date = fridays[2] if len(fridays) >= 3 else date(year, month, min(15,28))
    idx = EXPIRY_ORDER.index(letter) + int(year2) * 12
    return (letter + year2, idx, expiry_date)

def years_to_expiry(expiry_date, today=None):
    if expiry_date is None or pd.isna(expiry_date): return np.nan
    today = today or date.today()
    delta = expiry_date - today
    return max(delta.days / 365.0, 0.0)


# ------------------- Load files & preview -------------------
st.set_page_config(layout="wide", page_title="Options Strategy Scenario Tool",page_icon="📒")
st.title("SET50 Options & Futures Strategy Tool (finalized)")

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_STRATEGY_PATH = BASE_DIR / "data" / "st_template.json"
DEFAULT_MARKET_FUTURE_PATH = BASE_DIR / "data" / "market_data_S50.json"
DEFAULT_MARKET_PATH = BASE_DIR / "data" / "market_data_S50OPTION.json"

DEFAULT_MARKET_FUTURE_PATH2 = BASE_DIR / "data" / "market_data_SVF.json"
DEFAULT_MARKET_FUTURE_PATH3 = BASE_DIR / "data" / "market_data_GF.json"
DEFAULT_MARKET_FUTURE_PATH4 = BASE_DIR / "data" / "market_data_GF10.json"
DEFAULT_MARKET_FUTURE_PATH5 = BASE_DIR / "data" / "market_data_GO.json"

with st.sidebar.expander("Data file paths (change if needed)"):
    FUTURE_MARKET_PATH = Path(st.text_input("FUTURE Market JSON path", str(DEFAULT_MARKET_FUTURE_PATH)))
    OPTION_MARKET_PATH = Path(st.text_input("OPTION Market JSON path", str(DEFAULT_MARKET_PATH)))
    FUTURE_MARKET_PATH2 = Path(st.text_input("SVF FUTURE Market JSON path", str(DEFAULT_MARKET_FUTURE_PATH2)))
    FUTURE_MARKET_PATH3 = Path(st.text_input("GF FUTURE Market JSON path", str(DEFAULT_MARKET_FUTURE_PATH3)))
    FUTURE_MARKET_PATH4 = Path(st.text_input("GF10 FUTURE Market JSON path", str(DEFAULT_MARKET_FUTURE_PATH4)))
    FUTURE_MARKET_PATH5 = Path(st.text_input("GO FUTURE Market JSON path", str(DEFAULT_MARKET_FUTURE_PATH5)))
# load option market
try:
    df_market = pd.DataFrame(json.loads(OPTION_MARKET_PATH.read_text(encoding="utf-8")))
    df_market.columns = [c.strip() for c in df_market.columns]
except Exception as e:
    st.error(f"Cannot read option market JSON: {e}")
    st.stop()

# parse numeric-ish columns where present
# for col in df_market.columns:
#     if col not in ("Series","Name","Contract Month","Contract Year"):
#         df_market[col] = df_market[col].apply(parse_num)

# add parsed fields: TypeParsed, Strike, ExpiryIndex, ExpiryDate
parsed = df_market["Series"].apply(leg_type_from_series)
df_market["TypeParsed"] = parsed.apply(lambda x: x[0])
df_market["Strike"] = parsed.apply(lambda x: x[1])
eparse = df_market["Series"].apply(parse_expiry_code)
df_market["ExpiryCode"] = eparse.apply(lambda x: x[0])
df_market["ExpiryIndex"] = eparse.apply(lambda x: x[1])
# df_market["ExpiryDate"] = eparse.apply(lambda x: x[2])
df_market['ExpiryDate'] = pd.to_datetime(df_market['ExpiryDate']).dt.date

# load future market (optional)
try:
    df_market_Future = pd.DataFrame(json.loads(FUTURE_MARKET_PATH.read_text(encoding="utf-8")))
    # for col in df_market_Future.columns:
    #     if col != "Series":
    #         df_market_Future[col] = df_market_Future[col].apply(parse_num)
    eparse_f = df_market_Future["Series"].apply(parse_expiry_code)
    df_market_Future["ExpiryCode"] = eparse_f.apply(lambda x: x[0])
    df_market_Future["ExpiryIndex"] = eparse_f.apply(lambda x: x[1])
    # df_market_Future["ExpiryDate"] = eparse_f.apply(lambda x: x[2])
    df_market_Future['ExpiryDate'] = pd.to_datetime(df_market_Future['ExpiryDate']).dt.date

    df_market_Future2 = pd.DataFrame(json.loads(FUTURE_MARKET_PATH2.read_text(encoding="utf-8")))
    df_market_Future2['ExpiryDate'] = pd.to_datetime(df_market_Future2['ExpiryDate']).dt.date

    df_market_Future3 = pd.DataFrame(json.loads(FUTURE_MARKET_PATH3.read_text(encoding="utf-8")))
    df_market_Future3['ExpiryDate'] = pd.to_datetime(df_market_Future3['ExpiryDate']).dt.date

    df_market_Future4 = pd.DataFrame(json.loads(FUTURE_MARKET_PATH4.read_text(encoding="utf-8")))
    df_market_Future4['ExpiryDate'] = pd.to_datetime(df_market_Future4['ExpiryDate']).dt.date    

    df_market_Future5 = pd.DataFrame(json.loads(FUTURE_MARKET_PATH5.read_text(encoding="utf-8")))
    df_market_Future5['ExpiryDate'] = pd.to_datetime(df_market_Future5['ExpiryDate']).dt.date

except Exception:
    df_market_Future = pd.DataFrame()
    df_market_Future2 = pd.DataFrame()
    df_market_Future3 = pd.DataFrame()
    df_market_Future4 = pd.DataFrame()
    df_market_Future5 = pd.DataFrame()

# df_market
df_market = df_market[["Series", "OI (Contract)", "Days Left", "Last", "THEORETICAL", "INTRINSIC VALUE", "MONEYNESS", "Strike","Suggest","IV vs HV","Implied Vol (%)","Historical Vol (%)"]]
# df_market_Future
df_market_Future = df_market_Future[["Series", "OI (Contract)", "Last", "Bid", "Offer", "Vol (Contract)", "UNDERLYING PRICE", "ExpiryDate","Diff","Premuim vs Discount","Suggest"]]

df_market_Future2 = df_market_Future2[["Series", "OI (Contract)", "Last", "Bid", "Offer", "Vol (Contract)", "UNDERLYING PRICE", "ExpiryDate","Diff","Premuim vs Discount","Suggest"]]
df_market_Future3 = df_market_Future3[["Series", "OI (Contract)", "Last", "Bid", "Offer", "Vol (Contract)", "UNDERLYING PRICE", "ExpiryDate","Diff","Premuim vs Discount","Suggest"]]
df_market_Future4 = df_market_Future4[["Series", "OI (Contract)", "Last", "Bid", "Offer", "Vol (Contract)", "UNDERLYING PRICE", "ExpiryDate","Diff","Premuim vs Discount","Suggest"]]
df_market_Future5 = df_market_Future5[["Series", "OI (Contract)", "Last", "Bid", "Offer", "Vol (Contract)", "UNDERLYING PRICE", "ExpiryDate","Diff","Premuim vs Discount","Suggest"]]


# JSON preview for templates (stringify nested fields so Streamlit doesn't crash)
with st.expander("JSON & Market preview (read-only)"):
    if role_required(st.session_state, ["trader", "admin"]):


        tab1, tab2,tab3, tab4,tab5,tab6 = st.tabs(["Option", "SET50","SVF", "GF","GF10","GO"])
        tab1.dataframe(df_market, height=250)
        tab2.dataframe(df_market_Future, height=250)
        tab3.dataframe(df_market_Future2, height=250)        
        tab4.dataframe(df_market_Future3, height=250)
        tab5.dataframe(df_market_Future4, height=250)
        tab6.dataframe(df_market_Future5, height=250)

        
        st.markdown("---")
        st.text("Future : Discount > 3 pt --> Long")
        st.text("Future : Premium > 3 pt --> Short")
        st.text("Option : Overpriced --> Short")
        st.text("Option : Underpriced --> Long")
    else:
        st.info("🔒 You don't have permission to view this data.")

# ------------------- App controls -------------------
st.sidebar.header("Scenario & global settings")

###############################################
# Sidebar button to go Home
if st.sidebar.button("🏠 Back to HOME"):
    st.switch_page("HOME.py") 



