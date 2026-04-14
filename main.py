import streamlit as st
import pandas as pd
import sys
import os
from DB import *
import pyodbc
from datetime import datetime
import streamlit as st
from login import get_auth_url, exchange_code_for_token

if "user" not in st.session_state:
    st.session_state.user = None

code = st.query_params.get("code")

# 🔐 LOGIN FLOW
if st.session_state.user is None:
    if code:
        result = exchange_code_for_token(code)

        if "id_token_claims" in result:
            claims = result["id_token_claims"]

            st.session_state.user = {
                "name": claims.get("name"),
                "email": claims.get("preferred_username"),
                "oid": claims.get("oid"),
            }

            st.query_params.clear()
            st.rerun()
        else:
            st.error(result.get("error_description", "Login failed"))
            st.stop()
    else:
        # 🔥 AUTO REDIRECT TO MICROSOFT LOGIN
        login_url = get_auth_url()

        st.markdown(
            f'<meta http-equiv="refresh" content="0; url={login_url}">',
            unsafe_allow_html=True
        )
        st.stop()

# ✅ USER IS LOGGED IN
st.success(f"Signed in as {st.session_state.user['name']}")
st.write(st.session_state.user)

def get_db_connection():
    return get_connection()

#Main Conn Object
conn = get_db_connection()  

user = st.session_state.user

login = setLoggedInUser(conn, user)
# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="CRT PARS",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Top banner */
    .top-banner {
        background-color: #1a1a1a;
        color: white;
        padding: 10px 20px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 18px;
        font-weight: bold;
        margin-bottom: 10px;
    }
    /* Active sidebar item */
    .active-nav { background-color: #4a90d9; color: white; padding: 4px 8px; border-radius: 4px; }
    /* Red alert heading */
    .auto-alloc-heading { color: #cc0000; font-size: 18px; font-weight: bold; margin: 20px 0 8px; }
    /* Filter tag pills */
    .filter-tag {
        display: inline-block;
        background: #e0e0e0;
        border: 1px solid #aaa;
        border-radius: 4px;
        padding: 2px 8px;
        margin-right: 6px;
        font-size: 13px;
    }
    div[data-testid="stHorizontalBlock"] {
        gap: 0;
        padding: 0;
        margin: 0;
        align-items: center;
    }
    div[data-testid="stColumn"] {
        padding: 2px 8px !important;
    }
    hr {
        margin: 4px 0 !important;
    }
    div[data-testid="stToggle"] {
        margin: 0;
        padding: 0;
    }
</style>
""", unsafe_allow_html=True)

# ── Top Banner ────────────────────────────────────────────────────────────────
st.markdown("""
<div class="top-banner">
    <span>CRT</span>
    <span>Resource Allocation</span>
</div>
""", unsafe_allow_html=True)

# ── Top Nav Tabs ──────────────────────────────────────────────────────────────
top_nav = st.columns([1, 2, 1, 8])
with top_nav[0]:
    st.button("Home", use_container_width=True)
with top_nav[1]:
    st.button("Employee Self Service", use_container_width=True)
with top_nav[2]:
    st.button("Import Time Cards - ADMIN", use_container_width=True)

st.divider()

# ── Layout: Sidebar  +  Main Content ─────────────────────────────────────────
sidebar_col, main_col = st.columns([1, 5])

# ── LEFT SIDEBAR ──────────────────────────────────────────────────────────────
with sidebar_col:
    st.button("🏠 Home", use_container_width=True)

    with st.expander("👤 Employee Self Service", expanded=True):
        # Highlight active page
        st.markdown('<div class="active-nav">Timecard Allocations</div>', unsafe_allow_html=True)
        st.button("Approval Report Manager", use_container_width=True)
        st.button("Time Card Report", use_container_width=True)

    st.divider()
    st.button("🚪 Logout", use_container_width=True)
    uploaded_file = st.file_uploader("Import Excel", type=["xlsx", "xls"])
    if uploaded_file is not None:
        df = pd.read_excel(uploaded_file)
        st.dataframe(df)
        importTimeCards(df, conn)

# ── MAIN CONTENT ──────────────────────────────────────────────────────────────
with main_col:
    st.subheader("Time Card CRT")

    # ── Controls Row ─────────────────────────────────────────────────────────
    ctrl1, ctrl2, ctrl3, ctrl4 = st.columns([2, 3, 2, 2])

    with ctrl1:
        pay_period = st.selectbox(
            "Pay Periods",
            options=getPayPeriods(conn),
            index=0,
        )

    with ctrl2:
        employees = getEmployeesByPayPeriod(conn, pay_period, user)
        employee_name = st.selectbox(
            "Employee Name",
            options=employees,
            format_func=lambda e: e.full_name()
        )

    with ctrl3:
        manager_approve = st.checkbox("Manager – Check here to approve allocations")

    with ctrl4:
        employee_ack = st.checkbox("Employee – Check here to acknowledge allocations")

    # ── Grid 1: Time Card Allocations ─────────────────────────────────────────
    st.markdown("---")
    refresh_col, _ = st.columns([1, 8])
    with refresh_col:
        st.button("🔄 Refresh", key="refresh_grid1")
    
    
    if employee_name is not None:
        timecard_df = getSchedule(conn, employee_name.employee_code, pay_period)
        fund_options = getFundsByEmployee(conn, employee_name.employee_code)
        if timecard_df.empty:
            st.caption("No records to display.")
        else:
            # Table Header
            col1, col2, col3, col4, col5 = st.columns([0.5, 2, 2, 1.5, 1.5])
            col1.markdown("**&nbsp;**")
            col2.markdown("**Date**")
            col3.markdown("**Pay Type**")
            col4.markdown("**Total Hours**")
            col5.markdown("**Percentage**")

            st.markdown("<hr style='margin:2px 0; border:none; border-top:1px solid #eee;'>", unsafe_allow_html=True)
            task_options = getTasks(conn)

            
            for _, row in timecard_df.iterrows():
                schedule_id = row['ScheduleID']
                key = f"expanded_{schedule_id}"
                # Initialize session state
                if key not in st.session_state:
                    st.session_state[key] = False

                # Table Row
                col1, col2, col3, col4, col5 = st.columns([0.5, 2, 2, 1.5, 1.5])

                with col1:
                    arrow = "▼" if st.session_state[key] else "►"
                    if st.button(arrow, key=f"btn_{schedule_id}"):                       
                        st.session_state[key] = not st.session_state[key]
                        st.rerun()
                        
                        

                col2.write(row["Date"])
                col3.write(row["PayType"])
                col4.write(row["TotalHours"])
                col5.write(f"{row['Percentage']}%")

                # Expandable Allocation Section
                
                
                if st.session_state[f"expanded_{schedule_id}"]:
                    
                    with st.container():
                        allocations_df = getRecords(conn, schedule_id)

                        if allocations_df is None:
                            allocations_df = pd.DataFrame(columns=["ID", "Task", "Fund", "Hours"])
                        else:
                            allocations_df = allocations_df.copy()

                        editor_df = allocations_df[["ID", "Task", "Fund", "Hours"]].copy()

                        edited_df = st.data_editor(
                            editor_df,
                            column_order=["Task", "Fund", "Hours"],
                            column_config={
                                "ID": None,
                                "Task": st.column_config.SelectboxColumn("Task", options=task_options),
                                "Fund": st.column_config.SelectboxColumn("Fund", options=fund_options),
                                "Hours": st.column_config.NumberColumn("Hours", format="%.2f"),
                            },
                            num_rows="dynamic",
                            key=f"alloc_{schedule_id}"
                        )

                        edited_df = edited_df.dropna(how="all").copy()

                        total = pd.to_numeric(edited_df["Hours"], errors="coerce").fillna(0).sum()
                        st.write(f"Total Allocation: {total:.2f}")

                        if total > float(row['TotalHours']):
                            st.error(f"Total allocation cannot exceed {float(row['TotalHours'])}")

                        if st.button("💾 Save Allocations", key=f"save_{schedule_id}", disabled=total > float(row['TotalHours'])):
                            original_ids = set(allocations_df["ID"].dropna().astype(int))
                            edited_ids = set(edited_df["ID"].dropna().astype(int))
                            deleted_ids = original_ids - edited_ids

                            for deleted_id in deleted_ids:
                                deleteRecord(conn, int(deleted_id))

                            saveAllocations(conn, schedule_id, edited_df)
                            st.success("Saved!")

                    st.markdown("<hr style='margin:2px 0; border:none; border-top:1px solid #eee;'>", unsafe_allow_html=True)