# options_app.py
import pandas as pd
import numpy as np
import json
from pathlib import Path

import re
import calendar
from datetime import date
import streamlit as st
import matplotlib.pyplot as plt
from scipy.stats import norm
import itertools
import sys
from supabase import create_client
# Add parent directory (app/) to Python path
sys.path.append(str(Path(__file__).resolve().parent.parent))
# --- Setup Supabase ---
# --- Setup Supabase ---
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title="SET50 Strategy", layout="wide")
st.title("📈 SET50 Strategy Builder")

# --- Auth check ---
if "email" not in st.session_state:
    st.warning("👀 You can explore, but please login to save strategies.")
    user_email = None
else:
    user_email = st.session_state["email"]
    st.info(f"Logged in as: {user_email} ({st.session_state.get('role','viewer')})")

user_email = st.session_state.get("email", None)
user_role = st.session_state.get("role", "guest")

# Define permissions
is_logged_in = user_email is not None
is_trader_or_admin = user_role in ["trader", "admin"]

# Use this flag for disabling buttons
disabled = not is_trader_or_admin


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
st.set_page_config(layout="wide", page_title="Options Strategy Scenario Tool",page_icon="📋")
st.title("SET50 Options & Futures Strategy Tool (finalized)")

# default paths - adjust if different

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_STRATEGY_PATH = BASE_DIR / "data" / "st_template.json"
DEFAULT_MARKET_FUTURE_PATH = BASE_DIR / "data" / "market_data_S50.json"
DEFAULT_MARGIN_FUTURE_PATH = BASE_DIR / "data" / "margin_data_future.json"
DEFAULT_MARKET_PATH = BASE_DIR / "data" / "market_data_S50OPTION.json"
DEFAULT_MARGIN_PATH = BASE_DIR / "data" / "margin_data_option.json"

with st.sidebar.expander("Data file paths (change if needed)"):
    TEMPLATE_PATH = Path(st.text_input("STRATEGY JSON path", str(DEFAULT_STRATEGY_PATH)))
    FUTURE_MARKET_PATH = Path(st.text_input("FUTURE Market JSON path", str(DEFAULT_MARKET_FUTURE_PATH)))
    FUTURE_MARGIN_PATH = Path(st.text_input("FUTURE Margin JSON path", str(DEFAULT_MARGIN_FUTURE_PATH)))
    OPTION_MARKET_PATH = Path(st.text_input("OPTION Market JSON path", str(DEFAULT_MARKET_PATH)))
    OPTION_MARGIN_PATH = Path(st.text_input("OPTION Margin JSON path", str(DEFAULT_MARGIN_PATH)))

# load strategy json
try:
    STRATEGY_TEMPLATES = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
except Exception as e:
    STRATEGY_TEMPLATES = {}
    st.warning(f"Couldn't load strategy JSON: {e}")

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
except Exception:
    df_market_Future = pd.DataFrame()

# margins
try:
    df_margin = pd.DataFrame(json.loads(OPTION_MARGIN_PATH.read_text(encoding="utf-8")))
except Exception:
    df_margin = pd.DataFrame()
try:
    df_margin_Future = pd.DataFrame(json.loads(FUTURE_MARGIN_PATH.read_text(encoding="utf-8")))
except Exception:
    df_margin_Future = pd.DataFrame()

# JSON preview for templates (stringify nested fields so Streamlit doesn't crash)
try:
    df_temp_preview = pd.DataFrame.from_dict(STRATEGY_TEMPLATES, orient="index")
    for c in df_temp_preview.columns:
        df_temp_preview[c] = df_temp_preview[c].apply(lambda v: json.dumps(v) if isinstance(v, (list,dict)) else v)
except Exception:
    df_temp_preview = pd.DataFrame()
with st.expander("JSON & Market preview (read-only)"):
    if is_trader_or_admin:
        tab1, tab2,tab3, tab4,tab5 = st.tabs(["Option", "Future","Option margin", "Future margin","Template"])
        tab1.dataframe(df_market, height=250)
        tab2.dataframe(df_market_Future, height=250)
        tab3.dataframe(df_margin, height=250)
        tab4.dataframe(df_margin_Future, height=250)
        tab5.dataframe(df_temp_preview, height=250)
    else:
        st.info("🔒 You don't have permission to view this data.")

#Check default multiplier,S_manual from df_market_Future json
if not df_market_Future.empty:
    default_multiplier = df_market_Future.iloc[0]["MULTIPLER"]
    default_last = df_market_Future.iloc[0]["Last"] if (df_market_Future.iloc[0]["Last"] is None) else df_market_Future.iloc[0]["Bid"] 
    default_S_manual = df_market_Future.iloc[0]["UNDERLYING PRICE"] if (df_market_Future.iloc[0]["UNDERLYING PRICE"] is None) else default_last

# ------------------- App controls -------------------

st.sidebar.header("Scenario & global settings")
multiplier = int(st.sidebar.number_input("Contracts multiplier", value= default_multiplier if default_multiplier is not None and default_multiplier != 0 else 200, step=1))
S_manual = float(st.sidebar.number_input("Manual spot",value = default_S_manual if default_S_manual is not None and default_S_manual != 0 else 850.0,step=0.1,format="%.1f"))
fee_future = float(st.sidebar.number_input("Future fee per contract (THB)", value=83.567, step=0.001, format="%.3f"))
fee_option = float(st.sidebar.number_input("Option fee per contract (THB)", value=81.427, step=0.001, format="%.3f"))
#Portfolio rebalancing
st.sidebar.header("Portfolio settings")
init_balance = st.sidebar.number_input("Initial Balance", value=50000.00, step=1000.0, format="%.2f")
est_price = st.sidebar.number_input("Estimate Underlying Price", value=700.00, step=1.0, format="%.2f")

st.sidebar.header("Template")
template_choice = st.sidebar.selectbox("Choose template", ["Custom"] + list(STRATEGY_TEMPLATES.keys()))

with st.sidebar.expander("⚙️ option"):    
    T_scale = float(st.slider("Scale per-leg time to expiry (0.1x..2x)", 0.1, 2.0, 1.0, step=0.05))
    rf = float(st.number_input("Risk-free rate (annual decimal)", value=0.015, step=0.001, format="%.3f"))
    vol_shift_pct = float(st.slider("Global IV shift (%)", -80, 200, 0, step=1))


# ------------------- Build useful arrays and ATM references -------------------
unique_strikes = np.array(sorted(df_market["Strike"].dropna().unique())) if "Strike" in df_market.columns else np.array([])
unique_exp = np.array(sorted(df_market["ExpiryIndex"].dropna().unique())) if "ExpiryIndex" in df_market.columns else np.array([])

# find ATM strike index relative to spot_ref
spot_ref = S_manual if S_manual > 0 else (np.median(unique_strikes) if unique_strikes.size else 0)
atm_strike_idx = int(np.argmin(np.abs(unique_strikes - spot_ref))) if unique_strikes.size else None
atm_exp_idx = None
if unique_exp.size:
    # prefer expiry associated with ATM strike if available
    if atm_strike_idx is not None:
        atm_strike_val = unique_strikes[atm_strike_idx]
        atm_rows = df_market[np.isclose(df_market["Strike"], atm_strike_val)]
        if not atm_rows.empty and "ExpiryIndex" in atm_rows.columns:
            vals = atm_rows["ExpiryIndex"].dropna().values
            if vals.size:
                # most common expiry for that strike
                atm_exp_idx = int(pd.Series(vals).mode().iat[0])
    if atm_exp_idx is None:
        atm_exp_idx = int(unique_exp[int(len(unique_exp)/2)]) if unique_exp.size else None
#
# --- Load block from Supabase ---
st.subheader("📂 Load saved strategy")
load_state = False
missing_legs = []  # keep same structure

if user_email:
    # Fetch saved strategies for this user
    res = supabase.table("strategies").select("*").eq("email", user_email).execute()
    strategies = res.data if res.data else []

    if strategies:
        # Build selectbox with strategy names
        selected_name = st.selectbox(
            "Choose saved strategy",
            [s["name"] for s in strategies],
            key="load_strategy"
        )

        if st.button("Load selected"):
            # Find the chosen strategy
            strat = next(s for s in strategies if s["name"] == selected_name)

            content = strat.get("content", {})  # content dict inside row

            # Extract legs + selected_series
            legs_data = content.get("legs", [])
            selected_series = content.get("selected_series", [])

            # Restore into session_state
            st.session_state["selected_series"] = selected_series
            st.session_state["df_legs_saved"] = pd.DataFrame(legs_data)

            load_state = True
            template_choice = "Saved"

            st.success(f"✅ Loaded strategy '{selected_name}' from database")

# --- Initialize working vars ---
selected_series = st.session_state.get("selected_series", [])
df_legs_loaded = st.session_state.get("df_legs_saved", pd.DataFrame())



all_series = df_market["Series"].tolist() + (df_market_Future["Series"].tolist() if not df_market_Future.empty else [])
if template_choice == "Custom":
    selected_series = st.multiselect("Select series", all_series, default=all_series[:3],key="selected_series")

else:
    # build from template
    base_series = []
    comps = STRATEGY_TEMPLATES.get(template_choice, {}).get("components", [])
    used = set()
    for comp in comps:
        typ = comp.get("type")
        rs = int(comp.get("relative_strike", 0))
        re = int(comp.get("relative_expiry", 0))

        chosen = None
        target_strike = None
        target_exp = None

        # 1) compute target strike using index offsets on unique_strikes (ensures distinct offsets)
        if atm_strike_idx is not None and unique_strikes.size:
            target_idx = atm_strike_idx + rs
            if 0 <= target_idx < len(unique_strikes):
                target_strike = unique_strikes[target_idx]

        # 2) compute target expiry by index (offset in unique_exp)
        if atm_exp_idx is not None and unique_exp.size:
            try:
                base_pos = int(np.where(unique_exp == atm_exp_idx)[0][0])
                targ_pos = base_pos + re
                if 0 <= targ_pos < len(unique_exp):
                    target_exp = unique_exp[targ_pos]
            except Exception:
                # fallback: try atm_exp_idx + re if present
                candidate = atm_exp_idx + re
                if candidate in unique_exp:
                    target_exp = candidate

        # 3) exact match: strike + expiry + type
        if typ in ("Call", "Put") and target_strike is not None and target_exp is not None:
            cands = df_market[
                (np.isclose(df_market["Strike"], target_strike)) &
                (df_market["TypeParsed"] == typ) &
                (df_market["ExpiryIndex"] == target_exp)
            ]
            if not cands.empty:
                chosen = cands.iloc[0]["Series"]

        # 4) fallback: nearest strike on same expiry (bias downward for negative rs)
        if chosen is None and typ in ("Call", "Put") and target_exp is not None:
            cands_same_exp = df_market[df_market["ExpiryIndex"] == target_exp].copy()
            if not cands_same_exp.empty:
                base = target_strike if target_strike is not None else spot_ref
                cands_same_exp["strike_dist"] = np.abs(cands_same_exp["Strike"].fillna(base) - base)
                # tie-breaker preference: for negative rs prefer lower strike, for positive prefer higher
                if rs < 0:
                    cands_same_exp["pref"] = np.where(cands_same_exp["Strike"].fillna(base) <= base, 0, 1)
                else:
                    cands_same_exp["pref"] = np.where(cands_same_exp["Strike"].fillna(base) >= base, 0, 1)
                cands_sorted = cands_same_exp.sort_values(["strike_dist", "pref"])
                for s in cands_sorted["Series"].tolist():
                    if s not in used:
                        chosen = s
                        break

        # 5) fallback: same strike different expiry (nearest expiry)
        if chosen is None and typ in ("Call", "Put") and target_strike is not None:
            cands_same_strike = df_market[np.isclose(df_market["Strike"], target_strike)].copy()
            if not cands_same_strike.empty and atm_exp_idx is not None:
                cands_same_strike["exp_dist"] = np.abs(cands_same_strike["ExpiryIndex"].fillna(atm_exp_idx) - (target_exp if target_exp is not None else atm_exp_idx))
                cands_sorted = cands_same_strike.sort_values("exp_dist")
                for s in cands_sorted["Series"].tolist():
                    if s not in used:
                        chosen = s
                        break

        # 6) Future matching by expiry
        if chosen is None and typ == "Future" and not df_market_Future.empty and target_exp is not None:
            cands = df_market_Future[df_market_Future["ExpiryIndex"] == target_exp]
            if not cands.empty:
                for s in cands["Series"].tolist():
                    if s not in used:
                        chosen = s
                        break

        # 7) last resort: any candidate by type, nearest by strike+expiry score
        if chosen is None and typ in ("Call", "Put"):
            cands_any = df_market[df_market["TypeParsed"] == typ].copy()
            if not cands_any.empty:
                base_strike = target_strike if target_strike is not None else spot_ref
                base_exp = target_exp if target_exp is not None else (atm_exp_idx if atm_exp_idx is not None else 0)
                cands_any["score"] = np.abs(cands_any["Strike"].fillna(base_strike) - base_strike) + np.abs(cands_any["ExpiryIndex"].fillna(base_exp) - base_exp)
                cands_sorted = cands_any.sort_values("score")
                for s in cands_sorted["Series"].tolist():
                    if s not in used:
                        chosen = s
                        break

        if chosen: base_series.append(chosen)

        # if load_state:
        #     chosen = None


        if chosen and chosen not in used:
            selected_series.append(chosen)
            used.add(chosen)
        else:
            # do not append a placeholder series to selected_series; log & show a warning
            missing_legs.append({"type": typ, "qty": comp.get("qty", 0), "relative_strike": rs, "relative_expiry": re})
            st.warning(f"⚠️ Missing leg for template: {comp} (target_strike={target_strike}, target_exp={target_exp})")

# let user extend the template legs
    if load_state:
        selected_series = st.multiselect(
            f"Template: {template_choice} (add more legs if you want)",
            all_series,
            default=base_series,
            key="selected_series"
        )
    else:
        selected_series = st.multiselect(f"Template: {template_choice} (add more legs if you want)",all_series,default=base_series)

#info strategy
if template_choice == "Custom":
    st.info(f"📌 Custum selected.")
else:
    if template_choice != "Saved":
        st.subheader(f"📌 Template selected: {template_choice}.")
        st.info(f" {STRATEGY_TEMPLATES[template_choice]['tip']}")
        st.info(f" {STRATEGY_TEMPLATES[template_choice]['description']}")
        st.info(f" {STRATEGY_TEMPLATES[template_choice]['group']} ")
        st.info(f" {STRATEGY_TEMPLATES[template_choice]['components']} ")
    else:
        st.subheader(f"📌 Template selected: SAVED.")    
# ------------------- Build legs config UI (only include real selected_series) -------------------
st.markdown("### Configure legs (Qty positive = long, negative = short)")
legs = []
qty_defaults = []

#setting to convert Load to Custom


if template_choice != "Custom":
    for tpl_leg in STRATEGY_TEMPLATES.get(template_choice, {}).get("components", []):
        qty_defaults.append(int(tpl_leg.get("qty", 1)))

k = 0
for s in selected_series:
    col1, col2, col3, col4 = st.columns([4, 2, 2, 2])
    # option series
    if s in df_market["Series"].values:
        row = df_market[df_market["Series"] == s].iloc[0]
        opt = row["TypeParsed"]
        strike = row["Strike"]
        expiry = row["ExpiryDate"]
        expiry_idx = row.get("ExpiryIndex", np.nan)
        
        if load_state or template_choice == "Saved":
            default_price = df_legs_loaded[df_legs_loaded["Series"] == s]["TradePrice"].values[0]
            default_qty = df_legs_loaded[df_legs_loaded["Series"] == s]["Qty"].values[0]
        else:              
            default_price = choose_price_from_row(row.to_dict() if hasattr(row, "to_dict") else row)
            default_qty = qty_defaults[k] if (template_choice != "Custom" and k < len(qty_defaults)) else 1        
        
        iv = parse_num(row.get("IV LAST"))
        THEORETICAL = parse_num(row.get("THEORETICAL"))
        INTRINSICVALUE = parse_num(row.get("INTRINSIC VALUE"))
        MONEYNESS = row.get("MONEYNESS")
        DaysLeft = row.get("Days Left")



        with col1:
            st.markdown(f"**{s}** — {opt} strike={strike} Exp:{expiry}")
        with col2:
            if load_state or template_choice == "Saved":
                qty = int(default_qty)
                st.write(f"{default_qty}")
            else:
                qty = st.number_input(f"Qty ({s})", value=int(default_qty), step=1, key=f"qty_{s}_{template_choice}")
        with col3:
            if load_state or template_choice == "Saved":
                price_override = float(default_price)
                st.write(f"{default_price}")
            else:           
                price_override = st.number_input(f"Price override ({s})", value=float(default_price) if not np.isnan(default_price) else 0.0, format="%.2f", key=f"price_{s}_{template_choice}")

        with col4:
            if load_state or template_choice == "Saved":
                st.write("")
            else:        
                st.write(f"IV: {iv:.2f}%")

        # margin lookup

        margin_IM=margin_MM=np.nan
        mrow=df_margin[df_margin.Series==s]
        if not mrow.empty:
            if(qty>0):
                margin_IM=0; margin_MM=0
            else:
                margin_IM=parse_num(mrow.iloc[0].get("IM")); margin_MM=parse_num(mrow.iloc[0].get("MM"))
        # margin_IM = margin_MM = np.nan
        # if not df_margin.empty and "Series" in df_margin.columns:
        #     mrow = df_margin[df_margin["Series"] == s]
        #     if not mrow.empty:
        #         margin_IM = parse_num(mrow.iloc[0].get("IM"))
        #         margin_MM = parse_num(mrow.iloc[0].get("MM"))

        trade_price = price_override if price_override and price_override > 0 else default_price
        premium_total = trade_price * qty * multiplier if not np.isnan(trade_price) else np.nan

        legs.append({
            "Series": s,
            "Type": opt,
            "Strike": strike,
            "Expiry": expiry,
            "ExpiryIndex": expiry_idx,
            "Qty": int(qty),
            "TradePrice": trade_price,
            "PremiumTotal": premium_total,
            "IV": iv,
            "IM": margin_IM,
            "MM": margin_MM,
            "THEORETICAL": THEORETICAL,
            "INTRINSICVALUE": INTRINSICVALUE,
            "MONEYNESS": MONEYNESS,
            "DaysLeft": DaysLeft
        })

    # future series
    elif (not df_market_Future.empty) and (s in df_market_Future["Series"].values):
        row = df_market_Future[df_market_Future["Series"] == s].iloc[0]
        expiry = row["ExpiryDate"]
        expiry_idx = row.get("ExpiryIndex", np.nan)
        default_price = choose_price_from_row(row.to_dict() if hasattr(row, "to_dict") else row)
        default_qty = qty_defaults[k] if (template_choice != "Custom" and k < len(qty_defaults)) else 1
        iv = parse_num(row.get("IV LAST"))
        THEORETICAL = parse_num(row.get("THEORETICAL"))
        INTRINSICVALUE = parse_num(row.get("INTRINSIC VALUE"))
        MONEYNESS = row.get("MONEYNESS")
        DaysLeft = row.get("Days Left")

        with col1:
            st.markdown(f"**{s}** — Future Exp:{expiry}")
        with col2:
            qty = st.number_input(f"Qty ({s})", value=int(default_qty), step=1, key=f"qty_{s}_{template_choice}")
        with col3:
            price_override = st.number_input(f"Price override ({s})", value=float(default_price) if not np.isnan(default_price) else 0.0, format="%.6f", key=f"price_{s}_{template_choice}")
        with col4:
            st.write("Future")

        mrow=df_margin_Future[df_margin_Future.Series==s]
        margin_IM=margin_MM=np.nan
        if not mrow.empty:
            margin_IM=parse_num(mrow.iloc[0].get("IM")); margin_MM=parse_num(mrow.iloc[0].get("MM"))

        # margin_IM = margin_MM = np.nan
        # if not df_margin_Future.empty and "Series" in df_margin_Future.columns:
        #     mrow = df_margin_Future[df_margin_Future["Series"] == s]
        #     if not mrow.empty:
        #         margin_IM = parse_num(mrow.iloc[0].get("IM"))
        #         margin_MM = parse_num(mrow.iloc[0].get("MM"))

        trade_price = price_override if price_override and price_override > 0 else default_price
        legs.append({
            "Series": s,
            "Type": "Future",
            "Strike": trade_price,  # store price in Strike column for futures for plotting convenience
            "Expiry": expiry,
            "ExpiryIndex": expiry_idx,
            "Qty": int(qty),
            "TradePrice": trade_price,
            "PremiumTotal": 0.0,
            "IV": iv,
            "IM": margin_IM,
            "MM": margin_MM,
            "THEORETICAL": THEORETICAL,
            "INTRINSICVALUE": INTRINSICVALUE,
            "MONEYNESS": MONEYNESS,
            "DaysLeft": DaysLeft

        })
    else:
        # Shouldn't happen, but skip unknowns
        continue

    k += 1

# Also, if we had missing template legs, add read-only info rows with Qty=0 so table shows them (optional)
for miss in missing_legs:
    legs.append({
        "Series": f"Missing {miss['type']} (rs={miss['relative_strike']}, re={miss['relative_expiry']})",
        "Type": "Missing",
        "Strike": np.nan,
        "Expiry": np.nan,
        "ExpiryIndex": np.nan,
        "Qty": 0,
        "TradePrice": 0.0,
        "PremiumTotal": 0.0,
        "IV": 0.0,
        "IM": np.nan,
        "MM": np.nan,
        "THEORETICAL": np.nan,
        "INTRINSICVALUE": np.nan,
        "MONEYNESS": np.nan,
        "DaysLeft": np.nan
    })

df_legs = pd.DataFrame(legs)
st.subheader("Composed strategy legs")
st.dataframe(df_legs)

if df_legs.empty or df_legs["Qty"].abs().sum() == 0:
    st.warning("No legs with non-zero Qty. Add at least one leg to see payoff.")
    st.stop()

# ------------------- Payoff calculations -------------------
# compute S range from strikes
valid_strikes = df_legs["Strike"].dropna().values
if valid_strikes.size:
    minS = max(0.1, valid_strikes.min() * 0.6)
    maxS = valid_strikes.max() * 1.6
else:
    # fallback around spot_ref
    mid = spot_ref if spot_ref > 0 else 1000
    minS, maxS = max(0.1, mid * 0.6), mid * 1.6

S_range = np.linspace(minS, maxS, 401)

# override S_range if manual center
if S_manual and S_manual > 0:
    mid = S_manual
    spread = max(mid * 0.4, 50)
    S_range = np.linspace(max(0.1, mid - spread), mid + spread, 401)

total_pnl_expiry = np.zeros_like(S_range)
total_pnl_before = np.zeros_like(S_range)
for _, r in df_legs.iterrows():
    qty = int(r["Qty"])
    trade_price = parse_num(r["TradePrice"])
    if r["Type"] in ("Call", "Put"):
        total_pnl_expiry += payoff_for_leg_intrinsic(r["Type"], r["Strike"], qty, trade_price, multiplier, S_range)
        sigma = (r["IV"] / 100.0) if (not pd.isna(r["IV"]) and r["IV"] != 0) else np.nan
        if not np.isnan(sigma):
            sigma = max(1e-6, sigma * (1.0 + vol_shift_pct / 100.0))
        T_leg = years_to_expiry(r["Expiry"]) * T_scale if pd.notna(r["Expiry"]) else 0.25
        total_pnl_before += payoff_for_leg_bs(r["Type"], r["Strike"], qty, trade_price, multiplier, S_range, T_leg, rf, sigma)
    elif r["Type"] == "Future":
        total_pnl_expiry += payoff_for_leg_intrinsic("Future", 0, qty, trade_price, multiplier, S_range)
        total_pnl_before += payoff_for_leg_intrinsic("Future", 0, qty, trade_price, multiplier, S_range)
    else:
        # Missing placeholder (qty == 0) -> skip contributions
        pass

# breakevens and intercepts
sign_changes = np.where(np.diff(np.sign(total_pnl_expiry)) != 0)[0]
breakevens = [float(S_range[i]) for i in sign_changes]
y_intercept = float(total_pnl_expiry[0])
# summary stats
count_option = int((((((df_legs["Type"]=="Call") | (df_legs["Type"]=="Put"))).mul(df_legs["Qty"].abs()))).sum())
count_future = int(((df_legs["Type"]=="Future").mul(df_legs["Qty"].abs())).sum())
total_premium = df_legs["PremiumTotal"].sum(min_count=1) if "PremiumTotal" in df_legs.columns else 0.0
# margin: sum abs(qty) * per-contract IM/MM (if provided)
total_IM = (df_legs["Qty"].abs() * df_legs["IM"].fillna(0)).sum() if "IM" in df_legs.columns else 0.0
total_MM = (df_legs["Qty"].abs() * df_legs["MM"].fillna(0)).sum() if "MM" in df_legs.columns else 0.0
total_fee = fee_option * count_option * 2 + fee_future * count_future * 2

est_pl = float(np.interp(est_price, S_range,total_pnl_expiry))
equity = init_balance + est_pl
broke = equity < total_IM


# ------------------- Plot -------------------
st.subheader("Payoff chart")
fig, ax = plt.subplots(figsize=(10, 6))

# Main payoff lines
ax.plot(S_range, total_pnl_expiry, label="At Expiry (intrinsic)", linewidth=2)
ax.plot(
    S_range,
    total_pnl_before,
    label=f"Before Expiry (vol shift {vol_shift_pct:+.0f}%)",
    linestyle="--",
    linewidth=2,
)

# Shade positive (green) and negative (red) areas for expiry payoff
ax.fill_between(S_range, total_pnl_expiry, 0, where=(total_pnl_expiry >= 0), color="green", alpha=0.2)
ax.fill_between(S_range, total_pnl_expiry, 0, where=(total_pnl_expiry < 0), color="red", alpha=0.2)

# Breakeven lines
ax.axhline(0, linestyle="--", color="black")
for bx in breakevens:
    ax.axvline(bx, color="red", linestyle="--", alpha=0.6)
    ax.text(bx, 0, f"{bx:.1f}", color="red", ha="center", va="bottom")

# Label Y-intercept
ax.text(S_range[0], y_intercept, f"Y={y_intercept:.0f}", color="blue", va="bottom")

ax.set_xlabel("Underlying price")
ax.set_ylabel("Profit / Loss")
ax.grid(True)
ax.legend()

st.pyplot(fig)


# ------------------- Strategy detection (use relative expiry + strike-step by index) -------------------


def _normalize_offsets(items):
    if not items:
        return items
    min_exp = min([e for (_,_,_,e) in items])
    return [(t,q,rs,e-min_exp) for (t,q,rs,e) in items]

def _build_actual_pattern(df_legs_local, spot, strike_step_guess=None, atm_exp_idx_guess=None):
    strikes_present = df_legs_local["Strike"].dropna().unique()
    if len(strikes_present) == 0:
        return []
    atm_strike_local = strikes_present[np.argmin(np.abs(strikes_present - spot))]

    uniq = np.array(sorted(strikes_present))
    if uniq.size > 1:
        diffs = np.diff(uniq)
        pos = diffs[diffs > 0]
        strike_step_local = float(np.min(pos)) if pos.size else float(diffs[0])
    else:
        strike_step_local = float(strike_step_guess) if strike_step_guess else 5.0

    if "ExpiryIndex" in df_legs_local.columns and not df_legs_local["ExpiryIndex"].dropna().empty:
        atm_exp_idx_local = int(df_legs_local["ExpiryIndex"].dropna().mode().iat[0])
    else:
        atm_exp_idx_local = atm_exp_idx_guess

    actual = []
    for _, row in df_legs_local.iterrows():
        if pd.isna(row.get("Strike")): 
            continue
        try:
            rel_strike = int(np.round((row.get("Strike") - atm_strike_local) / strike_step_local))
        except:
            rel_strike = 0
        row_exp_idx = row.get("ExpiryIndex", np.nan)
        if pd.notna(row_exp_idx) and atm_exp_idx_local is not None:
            rel_expiry = int(row_exp_idx - atm_exp_idx_local)
        else:
            rel_expiry = 0
        actual.append((row.get("Type"), int(np.sign(row.get("Qty",0))), rel_strike, rel_expiry))
    return actual

def detect_strategy(df_legs_local, spot, strike_step_guess=None, atm_exp_idx_guess=None):
    if df_legs_local.empty:
        return None

    actual = _build_actual_pattern(df_legs_local, spot, strike_step_guess, atm_exp_idx_guess)
    if not actual:
        return None

    actual_norm = _normalize_offsets(actual)

    best_match = None
    best_score = float("inf")

    for name, template in STRATEGY_TEMPLATES.items():
        comps = template.get("components", [])
        tpl = [(leg.get("type"),
                int(np.sign(int(leg.get("qty",0)))),
                int(leg.get("relative_strike",0)),
                int(leg.get("relative_expiry",0)))
                for leg in comps]
        tpl_norm = _normalize_offsets(tpl)

        if len(tpl_norm) != len(actual_norm):
            continue

        best_tpl_score = float("inf")
        for actual_perm in itertools.permutations(actual_norm, len(tpl_norm)):
            score = 0
            ok = True
            for t_leg, a_leg in zip(tpl_norm, actual_perm):
                t_type,t_sign,t_rs,t_re = t_leg
                a_type,a_sign,a_rs,a_re = a_leg
                if t_type != a_type or t_sign != a_sign:
                    ok = False; break
                # allow strike mismatch of ±1 (score = diff)
                score += abs(t_rs - a_rs)
                # allow expiry mismatch of ±1 (score = diff)
                score += abs(t_re - a_re)
            if ok and score < best_tpl_score:
                best_tpl_score = score
        if best_tpl_score < best_score:
            best_score = best_tpl_score
            best_match = name

    return best_match




spot_detect = S_manual if S_manual > 0 else (np.median(df_legs["Strike"].dropna()) if not df_legs["Strike"].dropna().empty else spot_ref)
detected = detect_strategy(df_legs, spot_detect)
if detected:
    desc = STRATEGY_TEMPLATES.get(detected, {}).get("tip", "")
    st.success(f"📌 Detected strategy: **{detected}**")
    if desc:
        st.info(desc)
else:
    st.info("No standard strategy detected (custom mix).")

# ------------------- Summary -------------------
st.markdown("## <span style='color: blue;'>Summary</span>", unsafe_allow_html=True)

st.write(f"- Options: {count_option}, Futures: {count_future}")
st.write(f"- Net premium (sum premium * qty * multiplier): {total_premium:,.2f}")
st.write(f"- Total Initial Margin (IM) estimate: {total_IM:,.2f}")
st.write(f"- Total Maintenance Margin (MM) estimate: {total_MM:,.2f}")
st.write(f"- Estimated fees (round trip): {total_fee:,.2f}")
st.write(f"- Max profit @ expiry: {total_pnl_expiry.max():,.2f}")
st.write(f"- Max loss @ expiry: {total_pnl_expiry.min():,.2f}")
st.write(f"- Breakevens @ expiry: {', '.join(f'{b:.2f}' for b in breakevens) if breakevens else 'None'}")
st.write(f"- Y-intercept @ expiry (left edge): {y_intercept:,.2f}")

# ------------------- Risk: Broke Point -------------------
st.subheader("Broke-point Analysis")
equity_curve = init_balance + total_pnl_expiry
# Find underlying prices where equity crosses zero
sign_changes = np.where(np.diff(np.sign(equity_curve)) != 0)[0]
broke_prices = [S_range[i] for i in sign_changes]
if broke_prices:
    st.error(f"⚠️ Broke point(s): Underlying at {', '.join(f'{bp:.2f}' for bp in broke_prices)}")
else:
    st.success("✅ No broke point found within simulated price range.")

# Margin thresholds
margin_call_prices = [S_range[i] for i in range(len(S_range)) if equity_curve[i] < total_MM]
stop_out_prices    = [S_range[i] for i in range(len(S_range)) if equity_curve[i] < total_IM]

if margin_call_prices:
    st.warning(f"⚠️ Margin Call risk if price falls below {min(margin_call_prices):.2f}")
if stop_out_prices:
    st.error(f"❌ Stop-out risk if price falls below {min(stop_out_prices):.2f}")



#Report
st.subheader("What-if Report")
st.write(f"- Estimate underlying price: {est_price:,.2f}")
st.write(f"- P/L at {est_price:,.2f}: {est_pl:,.2f}")
st.write(f"- Equity: {equity:,.2f}")

if broke:
    st.error("⚠️ Equity below margin requirement → stop-out risk!")
else:
    st.success("✅ Equity above margin requirement")

# ------------------- Save & download -------------------
BASE_DIR = Path(__file__).resolve().parent.parent
st_dir = str(BASE_DIR / "output")
out_dir = Path(st_dir); out_dir.mkdir(exist_ok=True)
if st.button("Save outputs (CSV, XLSX, PNG)", disabled=disabled):
    df_legs.to_csv(out_dir / "strategy_legs.csv", index=False)
    try:
        df_legs.to_excel(out_dir / "strategy_legs.xlsx", index=False)
    except Exception:
        pass
    pd.DataFrame({"Spot": S_range, "P/L_expiry": total_pnl_expiry, "P/L_before": total_pnl_before}).to_csv(out_dir / "payoff_full.csv", index=False)
    fig.savefig(out_dir / "payoff_chart.png", dpi=150)
    st.success(f"Saved files to {out_dir.resolve()}")
st.download_button("Download strategy_legs.csv", data=df_legs.to_csv(index=False).encode(), file_name="strategy_legs.csv", mime="text/csv", disabled=disabled)
st.download_button("Download payoff_full.csv", data=pd.DataFrame({"Spot": S_range, "P/L_expiry": total_pnl_expiry, "P/L_before": total_pnl_before}).to_csv(index=False).encode(), file_name="payoff_full.csv", mime="text/csv", disabled=disabled)

#SAVE
# Prepare df_legs for saving
st.subheader("💾 Save Strategy")
strategy_name = st.text_input("Strategy name")

if st.button("Save Strategy", disabled=disabled):
    if not user_email:
        st.error("⚠️ Please login first.")
    elif not strategy_name.strip():
        st.error("⚠️ Please enter a strategy name.")
    else:
        # Convert DataFrame for JSON storage
        df_save = df_legs.copy()
        df_save["Expiry"] = df_save["Expiry"].astype(str)  # JSON safe
        save_payload = {
                "entry_date": str(date.today()),
                "selected_series": selected_series,
                "legs": df_save.to_dict(orient="records")
            }
        strategy_content = save_payload

        # Save to Supabase (always inserts a new row)
        user = supabase.auth.get_user()
        supabase.table("strategies").insert(
            {
                "email": user_email,
                "name": strategy_name,
                "content": strategy_content,
                "user_id": user.user.id  # ดึง user_id จาก session                
            }
        ).execute()

        st.success(f"✅ Strategy '{strategy_name}' saved for {user_email}")

# --- Load saved strategies ---
if user_email:
    st.subheader("📂 My Saved Strategies")
    res = supabase.table("strategies").select("*").eq("email", user_email).execute()

    if res.data:
        for strat in res.data:
            with st.expander(strat["name"]):
                df_loaded = pd.DataFrame(strat["content"])
                st.dataframe(df_loaded)
    else:
        st.info("No saved strategies yet.")



if not user_email or not user_role:
    st.sidebar.warning("⚠️ Please log in first. for more advance detail.")
    #click to HOME
else:
# Now you can safely use user["role"]
    st.sidebar.write(f"Welcome {user_email} ({user_role})")
###############################################

# Sidebar button to go Home
if st.sidebar.button("🏠 Back to Home"):
    st.switch_page("HOME.py")
# Info message for guests
if not is_logged_in:
    st.sidebar.info("👤 You are in guest mode. Login with Google to enable view more pages ('Viewer' mode) or donate to 'Trader' mode for save & advanced features.")
elif not is_trader_or_admin:
    st.sidebar.warning("⚠️ Your role is Viewer. Some functions are disabled.")