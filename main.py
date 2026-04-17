import streamlit as st
import pandas as pd
import sys
import os
from Controllers.DB import *
import pyodbc
from datetime import datetime
from login import get_auth_url, exchange_code_for_token
from Classes import *
from views import timecard_allocations, approval_report_manager, time_card_report
from Controllers.timecardAllocationController import *

# ── Page config (must be first) ───────────────────────────────────────────────
st.set_page_config(
    page_title="CRT PARS",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Session State Init ────────────────────────────────────────────────────────
if "user" not in st.session_state:
    st.session_state.user = None

if "active_page" not in st.session_state:
    st.session_state.active_page = "Timecard Allocations"

code = st.query_params.get("code")

# ── Login Flow ────────────────────────────────────────────────────────────────
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
        login_url = get_auth_url()
        st.markdown(
            f'<meta http-equiv="refresh" content="0; url={login_url}">',
            unsafe_allow_html=True,
        )
        st.stop()

# ── DB Connection ─────────────────────────────────────────────────────────────
conn = get_connection()
user = st.session_state.user



# ── Logout Handler ────────────────────────────────────────────────────────────
if st.query_params.get("logout") == "true":
    st.session_state.user = None
    st.query_params.clear()
    st.rerun()

# ── Global CSS + Fixed Header ─────────────────────────────────────────────────
initials = "".join([p[0].upper() for p in user['name'].split()[:2]])

st.markdown(f"""
<style>
    /* ── Reset Streamlit chrome ── */
    #MainMenu, footer, header {{ visibility: hidden; }}
    .block-container {{
        padding-top: 80px !important;
        padding-bottom: 2rem !important;
        max-width: 100% !important;
    }}

    /* ── Fixed top header ── */
    .app-header {{
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        z-index: 9999;
        height: 56px;
        background: #0f172a;
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0 28px;
        box-shadow: 0 2px 12px rgba(0,0,0,0.5);
    }}
    .header-left {{
        display: flex;
        align-items: center;
        gap: 12px;
    }}
    .header-badge {{
        background: #3b82f6;
        color: white;
        font-size: 11px;
        font-weight: 800;
        letter-spacing: 0.12em;
        padding: 3px 8px;
        border-radius: 4px;
    }}
    .header-title {{
        font-size: 15px;
        font-weight: 600;
        color: #f1f5f9;
        letter-spacing: 0.01em;
    }}
    .header-right {{
        display: flex;
        align-items: center;
        gap: 10px;
    }}
    .user-chip {{
        background: #1e293b;
        border: 1px solid #2d3f55;
        border-radius: 24px;
        padding: 4px 14px 4px 6px;
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 13px;
        color: #cbd5e1;
        font-weight: 500;
    }}
    .user-avatar {{
        width: 28px;
        height: 28px;
        border-radius: 50%;
        background: linear-gradient(135deg, #3b82f6, #6366f1);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 11px;
        font-weight: 800;
        color: white;
        flex-shrink: 0;
        letter-spacing: 0.05em;
    }}

    /* ── Sub-nav bar ── */
    .sub-nav {{
        background: #f8fafc;
        border-bottom: 1px solid #e2e8f0;
        padding: 0;
        margin-bottom: 0;
    }}

    /* ── Active sidebar nav item ── */
    .active-nav {{
        background: #3b82f6;
        color: white;
        padding: 5px 10px;
        border-radius: 6px;
        font-size: 13px;
        font-weight: 500;
        margin-bottom: 4px;
        display: block;
    }}

    /* ── Column layout reset ── */
    div[data-testid="stHorizontalBlock"] {{
        align-items: flex-start !important;
        gap: 0 !important;
        padding: 0 !important;
        margin-top: 0 !important;
    }}
    div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {{
        padding-top: 0 !important;
        margin-top: 0 !important;
    }}
    div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] > div {{
        padding-top: 0 !important;
        margin-top: 0 !important;
    }}
    div[data-testid="stColumn"] {{
        padding: 2px 8px !important;
    }}

    /* ── Sidebar section label ── */
    .sidebar-label {{
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        color: #9ca3af;
        padding: 8px 2px 4px;
    }}

    /* ── Page section label ── */
    .page-title {{
        font-size: 20px;
        font-weight: 700;
        color: #0f172a;
        margin: 0 0 2px 0;
        padding: 0;
    }}
    .page-subtitle {{
        font-size: 12px;
        color: #94a3b8;
        margin-bottom: 12px;
    }}

    hr {{ margin: 6px 0 !important; }}
    div[data-testid="stToggle"] {{ margin: 0; padding: 0; }}
    div[data-testid="stVerticalBlockBorderWrapper"] {{
        border: 1px solid #e5e7eb !important;
        border-radius: 8px !important;
        padding: 6px 10px !important;
        background: white !important;
    }}
    .logout-btn {{
        background: #1e293b;
        border: 1px solid #475569;
        border-radius: 6px;
        color: #cbd5e1 !important;
        font-size: 15px;
        font-weight: bold;
        padding: 5px 12px;
        text-decoration: none !important;
        cursor: pointer;
        transition: all 0.15s ease;
    }}
    .logout-btn:hover {{
        background: #dc2626;
        border-color: #dc2626;
        color: white !important;
    }}
</style>

<!-- Always-visible fixed header -->
<div class="app-header">
    <div class="header-left">
        <span class="header-badge">CRT</span>
        <span class="header-title">Payroll Allocation</span>
    </div>
    <div class="header-right">
        <div class="user-chip">
            <div class="user-avatar">{initials}</div>
            {user['name']}
        </div>
        <a href="?logout=true" class="logout-btn">Logout</a>
    </div>
</div>
""", unsafe_allow_html=True)

st.divider()

login = setLoggedInUser(conn, user)
isManager = login[0].isManager()

# ── Two-Column Layout ─────────────────────────────────────────────────────────
sidebar_col, main_col = st.columns([1, 5])

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with sidebar_col:
    with st.expander("Employee Self Service", expanded=True):
        #limit page choices depended on if manager 
        pages = [
        "Timecard Allocations",
        "Approval Report Manager",
        "Time Card Report"
        ] if isManager else [
            "Timecard Allocations",
            "Time Card Report"
        ]
        for page in pages:
            is_active = st.session_state.active_page == page
            if is_active:
                st.markdown(f'<div class="active-nav">{page}</div>', unsafe_allow_html=True)
            else:
                if page == "Time Card Report":
                    employee_code = login[0].employee_code
                    managing_dept = login[0].managing_department
                    dept_code = login[0].dept_code
                    print(login[0].managing_department)
                    if not isManager:
                            st.link_button("Time Card Report", f"https://app.powerbi.com/links/tOiI-kPzTl?ctid=31c347a9-3e62-4167-b697-eacfb065e074&pbi_source=linkShare&filter=Invoked_x0020_function/EmployeeCode eq '{employee_code}'", use_container_width=True)
                    else:
                            st.link_button("Time Card Report", f"https://app.powerbi.com/links/tOiI-kPzTl?ctid=31c347a9-3e62-4167-b697-eacfb065e074&pbi_source=linkShare&filter=Invoked_x0020_function/DepartmentCode eq '{managing_dept}' or Invoked_x0020_function/DepartmentCode eq '{dept_code}'", use_container_width=True)
                else:
                    if st.button(page, use_container_width=True, key=page):
                        st.session_state.active_page = page
                        st.rerun()

    st.markdown('<p class="sidebar-label">Import</p>', unsafe_allow_html=True)
    uploaded_file = st.file_uploader("Excel file", type=["xlsx", "xls"], label_visibility="collapsed")
    if uploaded_file is not None:
        df = pd.read_excel(uploaded_file)
        st.dataframe(df)
        importTimeCards(df, conn)

# ── MAIN CONTENT ──────────────────────────────────────────────────────────────
with main_col:
    
    match st.session_state.active_page:
        case "Timecard Allocations":
            timecard_allocations.render(conn, user, login)
        case "Approval Report Manager":
            approval_report_manager.render(conn, user, login)
        case "Time Card Report":
            st.markdown('<script>window.open("https://app.powerbi.com/links/tOiI-kPzTl?ctid=31c347a9-3e62-4167-b697-eacfb065e074&pbi_source=linkShare", "_blank");</script>', unsafe_allow_html=True)