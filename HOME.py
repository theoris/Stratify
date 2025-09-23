# HOME.py
import streamlit as st
import jwt  # pyjwt
from supabase import create_client
from streamlit_oauth import OAuth2Component

# --- Load secrets from Streamlit Cloud ---
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

GOOGLE_CLIENT_ID = st.secrets["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET = st.secrets["GOOGLE_CLIENT_SECRET"]

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"

# Detect environment for redirect
REDIRECT_URI = (
    "http://localhost:8501"  # local dev
    if "LOCAL_DEV" in st.secrets
    else "https://stratifyth.streamlit.app/"
)

# --- Init OAuth2 component ---
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
# st.sidebar.title("🔑 Authentication")

user_role = st.session_state.get("role", "guest")
is_trader_or_admin = user_role in ["trader", "admin"]
if not is_trader_or_admin:
    expan = st.sidebar.expander("Donate for advance usage"):
    expan.write("via USDT (BEP20) : 0x696D4c64d126E6d4fdB704aCd1e8f7B1d443c910")
    expan.image("img/donate.png", caption="QRCODE 0x696D4c64d126E6d4fdB704aCd1e8f7B1d443c910")

if "email" not in st.session_state:
    # Show Google login button
    result = oauth2.authorize_button(
        "Login with Google",
        redirect_uri=REDIRECT_URI,
        scope="openid email profile",
    )

    if result:
        email = None

        # Try to extract id_token
        id_token = result.get("id_token") or result.get("token", {}).get("id_token")

        if id_token:
            payload = jwt.decode(id_token, options={"verify_signature": False})
            email = payload.get("email")

        if email:
            st.session_state["email"] = email

            # Check if any users exist → first login rule
            existing = supabase.table("users").select("id").execute()

            if not existing.data:
                # First ever user → force admin
                supabase.table("users").upsert({"email": email, "role": "admin"}, on_conflict="email").execute()
                st.session_state["role"] = "admin"
            else:
                # All other logins → upsert ensures no duplicate error
                supabase.table("users").upsert({"email": email}, on_conflict="email").execute()
                role_res = supabase.table("users").select("role").eq("email", email).execute()
                st.session_state["role"] = role_res.data[0]["role"] if role_res.data else "viewer"


           

            st.success(f"✅ Logged in as {email}")
            st.rerun()
        else:
            st.error("⚠️ Could not extract email from Google login response")
            st.write("Debug result:", result)

else:
    email = st.session_state["email"]
    role = st.session_state.get("role", "viewer")
    st.sidebar.success(f"✅ Logged in as: {email} ({role})")

    if st.sidebar.button("Logout"):
        st.session_state.clear()
        st.rerun()

