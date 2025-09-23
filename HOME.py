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

if "email" not in st.session_state:
    # 🔹 MUST include redirect_uri + scope
    result = oauth2.authorize_button(
        "Login with Google",
        redirect_uri=REDIRECT_URI,
        scope="openid email profile",
    )

    if result:
        email = result["id_token"]["email"]
        st.session_state["email"] = email
        st.success(f"Welcome {email}")
else:
    st.sidebar.success(f"✅ Logged in as: {st.session_state['email']}")
    if st.sidebar.button("Logout"):
        st.session_state.clear()
        st.rerun()
    # # --- Signup ---
    # elif choice == "Signup":
    #     st.subheader("Signup")
    #     email = st.text_input("Email")
    #     password = st.text_input("Password", type="password")
    #     confirm = st.text_input("Confirm Password", type="password")

    #     if st.button("Create Account"):
    #         if not email or not password:
    #             st.warning("⚠️ Email and password required")
    #         elif password != confirm:
    #             st.warning("⚠️ Passwords do not match")
    #         else:
    #             if add_user(email, password):
    #                 st.session_state["email"] = email
    #                 st.session_state["role"] = "viewer"  # default role
    #                 st.success(f"🎉 Account created and logged in as {email}")
    #                 st.rerun()
    #             else:
    #                 st.error("❌ Email already registered")


# Sidebar navigation
st.sidebar.markdown("---")
st.sidebar.markdown("📂 Pages:")
st.sidebar.page_link("pages/1_SET50.py", label="SET50 Strategy")
