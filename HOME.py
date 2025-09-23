# Home.py
import streamlit as st
import os
from supabase_client import supabase
from streamlit_oauth import OAuth2Component


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


# --- OAuth config ---
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"

REDIRECT_URI = (
    "http://localhost:8501"
    if os.getenv("LOCAL_DEV")
    else "https://your-streamlit-app.streamlit.app"
)

oauth2 = OAuth2Component(
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    AUTHORIZE_URL,
    TOKEN_URL,
    REDIRECT_URI,
    ["openid", "email", "profile"],
)

st.sidebar.title("🔑 Authentication")
# If user already logged in → show welcome + logout
if "email" not in st.session_state:
    result = oauth2.authorize_button("Login with Google")
    if result:
        email = result["id_token"]["email"]
        st.session_state["email"] = email

        # Insert/upsert into Supabase
        supabase.table("users").upsert({"email": email}).execute()

        # Fetch role
        role_res = supabase.table("users").select("role").eq("email", email).execute()
        st.session_state["role"] = role_res.data[0]["role"] if role_res.data else "viewer"

        st.rerun()
else:
    email = st.session_state["email"]
    role = st.session_state.get("role", "viewer")

    st.sidebar.success(f"✅ Logged in as {email} ({role})")

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
