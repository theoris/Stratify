# Home.py
import streamlit as st
import os
from supabase_client import supabase
from streamlit_oauth import OAuth2Component

# --- Load secrets ---
GOOGLE_CLIENT_ID = st.secrets["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET = st.secrets["GOOGLE_CLIENT_SECRET"]

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"

# --- Redirect URI (local vs deployed) ---
REDIRECT_URI = (
    "http://localhost:8501"
    if "LOCAL_DEV" in st.secrets
    else "https://stratifyth.streamlit.app/"
)

# --- Create OAuth2 object ---
oauth2 = OAuth2Component(
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    AUTHORIZE_URL,
    TOKEN_URL,
)

st.set_page_config(page_title="Options & Futures Strategy Tool", layout="wide",page_icon="📖")
st.title("📊 Options & Futures Strategy Tool")
st.markdown("""
Welcome to the **multi-index Options & Futures Strategy Tool**.  

Use the menu on the left sidebar to switch between indices:  
- **SET50** — Thai Index Options & Futures  
- **SVF** — SVF Futures
- **GF10** — GF10 Futures  
- **GF50** — GF50 Futures
- **GO** — GO Futures
- **Portfolio** — report

Each page contains the **same tool structure** but loads different JSON market & margin data.  
""")

st.info("👈 Choose an index page from the sidebar to get started!")

# --- Sidebar ---
st.sidebar.title("🔑 Authentication")

if result:
    # Different versions of streamlit-oauth return token differently
    email = None

    # Case 1: id_token directly in result
    if "id_token" in result:
        from jwt import decode
        id_token = result["id_token"]
        # decode the JWT (without verifying for simplicity)
        payload = decode(id_token, options={"verify_signature": False})
        email = payload.get("email")

    # Case 2: id_token nested under token
    elif "token" in result and "id_token" in result["token"]:
        from jwt import decode
        id_token = result["token"]["id_token"]
        payload = decode(id_token, options={"verify_signature": False})
        email = payload.get("email")

    if email:
        st.session_state["email"] = email
        st.success(f"✅ Welcome {email}")
    else:
        st.error("⚠️ Could not extract email from Google login response.")
        st.write("Debug result:", result)



# Sidebar navigation
st.sidebar.markdown("---")
st.sidebar.markdown("📂 Pages:")
st.sidebar.page_link("pages/1_SET50.py", label="SET50 Strategy")
