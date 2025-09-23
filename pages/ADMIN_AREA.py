import sys
from pathlib import Path
from supabase_client import supabase
import streamlit as st
# Add parent directory (app/) to Python path
sys.path.append(str(Path(__file__).resolve().parent.parent))

st.set_page_config(page_title="Admin Dashboard", layout="wide",page_icon="📋")
st.title("👑 Admin Dashboard")
# ADMIN_AREA.py


# --- Require login ---
if "email" not in st.session_state:
    st.error("⛔ Please login first (via Home page).")
    st.stop()

if st.session_state.get("role") != "admin":
    st.error("⛔ Only admins can access this page.")
    st.stop()

st.success("✅ Welcome, Admin!")

# --- Fetch all users from Supabase ---
res = supabase.table("users").select("id, email, role, created_at").execute()
users = res.data if res.data else []

if not users:
    st.info("No users found.")
else:
    st.subheader("Registered Users")

    for u in users:
        col1, col2, col3 = st.columns([4, 3, 2])

        with col1:
            st.write(f"📧 **{u['email']}** — ({u['role']})")

        with col2:
            new_role = st.selectbox(
                "Change Role",
                ["viewer", "trader", "admin"],
                index=["viewer", "trader", "admin"].index(u["role"]),
                key=f"role_{u['id']}",
            )
            if new_role != u["role"]:
                if st.button(f"Update {u['email']}", key=f"update_{u['id']}"):
                    supabase.table("users").update({"role": new_role}).eq("id", u["id"]).execute()
                    st.success(f"Role updated → {new_role}")
                    st.rerun()

        with col3:
            if st.button(f"🗑️ Delete", key=f"delete_{u['id']}"):
                supabase.table("users").delete().eq("id", u["id"]).execute()
                st.warning(f"Deleted {u['email']}")
                st.rerun()
