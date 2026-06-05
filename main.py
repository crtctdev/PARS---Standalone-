import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import io
from datetime import datetime, date
from streamlit_calendar import calendar as st_calendar
from Controllers.DB import *
from login import get_auth_url, exchange_code_for_token, render_report, check_pars_group_membership
from Classes import *
from views import timecard_allocations, approval_report_manager, time_card_report
from Controllers.timecardAllocationController import *
from History.importHistoryController import logImport, getImportHistory


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

if "file_uploader_key" not in st.session_state:
    st.session_state.file_uploader_key = 0
if "import_message" not in st.session_state:
    st.session_state.import_message = None
if "db_employee_codes" not in st.session_state:
    st.session_state.db_employee_codes = None

code = st.query_params.get("code")

# ── Login Flow ────────────────────────────────────────────────────────────────
if st.session_state.user is None:
    if code:
        result = exchange_code_for_token(code)
        if "id_token_claims" in result:
            claims = result["id_token_claims"]
            if not check_pars_group_membership(claims.get("oid")):
                st.error("Access denied. You must be a member of the PARS security group to use this application.")
                st.stop()
            st.session_state.user = {
                "name": claims.get("name"),
                #Throw in here to spoof as other people
                "email": "rakhudum@crtct.org",
                "oid": claims.get("oid"),
            }
            st.query_params.clear()
            st.rerun()
        else:
            err = result.get("error_description", "")
            if "AADSTS54005" in err:
                st.warning("Your login link has already been used. Please refresh the page and try again.")
            else:
                st.error(err or "Login failed.")
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
        padding: 2px 3px !important;
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
    </div>
</div>
""", unsafe_allow_html=True)

st.divider()

login = setLoggedInUser(conn, user)

if not login:
    st.error(f"Your account ({user['email']}) is not set up in the system. Please contact your administrator.")
    st.stop()


admins_df = run_query(conn, "SELECT * FROM dbo.Admins")
admin_emails = set(admins_df["Email"].str.lower().tolist()) if admins_df is not None and not admins_df.empty else set()
isAdmin = user["email"].lower() in admin_emails
isManager = isAdmin or login[0].isManager()

if st.session_state.db_employee_codes is None:
    emp_df = run_query(conn, "SELECT EmployeeCode FROM dbo.vw_EmployeeInformation")
    st.session_state.db_employee_codes = emp_df["EmployeeCode"].tolist() if emp_df is not None and not emp_df.empty else []


# ── Two-Column Layout ─────────────────────────────────────────────────────────
sidebar_col, main_col = st.columns([1, 5])

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with sidebar_col:

    if "cal_open" not in st.session_state:
        st.session_state.cal_open = False
    if "cal_selected_date" not in st.session_state:
        st.session_state.cal_selected_date = None

    @st.fragment
    def calendar_section():
        if "cal_selected_date" not in st.session_state:
            st.session_state.cal_selected_date = None

        cal_arrow = "▼" if st.session_state.cal_open else "►"
        if st.button(f"{cal_arrow} Planning Calendar", use_container_width=True, key="cal_toggle"):
            st.session_state.cal_open = not st.session_state.cal_open

        if st.session_state.cal_open:
            emp_code = login[0].employee_code
            all_notes_df = getAllNotesByEmployee(conn, emp_code)
            cal_events = []
            if all_notes_df is not None and not all_notes_df.empty:
                for d in all_notes_df["Date"].unique():
                    cal_events.append({
                        "title": "●",
                        "start": f"{str(d)[:4]}-{str(d)[4:6]}-{str(d)[6:8]}",
                        "display": "background",
                        "backgroundColor": "#3b82f6",
                    })

            cal_result = st_calendar(
                events=cal_events,
                options={
                    "initialView": "dayGridMonth",
                    "headerToolbar": {"left": "prev,next", "center": "title", "right": ""},
                    "contentHeight": "auto",
                    "selectable": True,
                    "dayMaxEvents": True,
                },
                custom_css="""
                    .fc { font-size: clamp(9px, 4.5vw, 13px); }
                    .fc-toolbar-title { font-size: 1.1em !important; }
                    .fc-button { padding: 0.15em 0.4em !important; font-size: 0.85em !important; }
                    .fc-daygrid-day-number { font-size: 0.85em; }
                    .fc-col-header-cell { font-size: 0.8em; }
                """,
                callbacks=["dateClick"],
                key="planning_cal",
            )

            clicked = (cal_result or {}).get("dateClick", {}).get("date", "")
            if clicked:
                try:
                    st.session_state.cal_selected_date = date.fromisoformat(clicked[:10])
                except ValueError:
                    pass

            sel = st.session_state.cal_selected_date
            if sel:
                fund_options = getFundsByEmployee(conn, emp_code)
                task_options = getTasks(conn)

                existing = getNotes(conn, emp_code, sel)
                notes_df = existing.copy() if existing is not None else pd.DataFrame(columns=["ID", "Task", "Fund", "Hours"])

                edited_notes = st.data_editor(
                    notes_df[["ID", "Task", "Fund", "Hours"]],
                    column_order=["Task", "Fund", "Hours"],
                    column_config={
                        "ID": None,
                        "Task": st.column_config.SelectboxColumn("Task", options=task_options),
                        "Fund": st.column_config.SelectboxColumn("Fund", options=fund_options),
                        "Hours": st.column_config.NumberColumn("Hours", format="%.2f"),
                    },
                    num_rows="dynamic",
                    key=f"notes_editor_{sel}",
                )

                if st.button("💾 Save Notes", key="save_notes", use_container_width=True):
                    original_ids = set(notes_df["ID"].dropna().astype(int))
                    edited_ids = set(edited_notes["ID"].dropna().astype(int))
                    for del_id in (original_ids - edited_ids):
                        deleteNote(conn, int(del_id))
                    saveNote(conn, emp_code, sel, edited_notes)

    calendar_section()

    with st.expander("Employee Self Service", expanded=True):
        pages = [
        "Timecard Allocations",
        "Approval Report Manager",
        #"Time Card Report"
        ] if isManager else [
            "Timecard Allocations",
            #"Time Card Report"
        ]
        for page in pages:
            is_active = st.session_state.active_page == page
            if is_active:
                st.markdown(f'<div class="active-nav">{page}</div>', unsafe_allow_html=True)
            else:
                if st.button(page, use_container_width=True, key=page):
                    st.session_state.active_page = page
                    st.rerun()

    if isAdmin:
        st.markdown('<p class="sidebar-label">Import</p>', unsafe_allow_html=True)

        if st.session_state.import_message:
            msg_type, msg_text = st.session_state.import_message
            if msg_type == "error":
                st.error(msg_text)
            elif msg_type == "warning":
                st.warning(msg_text)
            else:
                st.success(msg_text)
            st.session_state.import_message = None

        uploaded_file = st.file_uploader("Excel file", type=["xlsx", "xls"], label_visibility="collapsed", key=st.session_state.file_uploader_key)

        if uploaded_file is not None:
            with st.spinner("Importing time cards..."):
                df = pd.read_excel(uploaded_file)
                required_cols = {"EECode", "InPunchTime", "EarnHours", "EarnCode"}
                if df.empty or not required_cols.issubset(df.columns):
                    st.session_state.import_message = ("error", "Upload rejected: file is empty or missing required columns (EECode, InPunchTime, EarnHours, EarnCode).")
                    st.session_state.file_uploader_key += 1
                    st.rerun()
                existing, missing, added, pay_period, pay_period_start = importTimeCards(df, conn)

                import_codes = [str(c).strip() for c in df["EECode"].unique()]
                unrepresented = [c for c in st.session_state.db_employee_codes if c not in import_codes]
                auto_allocated = autoAllocateSalariedEmployees(conn, pay_period, pay_period_start, unrepresented)

                allocated_tc_df = run_query(conn, "SELECT EmployeeCode FROM dbo.Time_Card WHERE PayPeriod = ?", [pay_period])
                allocated_codes = set(allocated_tc_df["EmployeeCode"].tolist()) if allocated_tc_df is not None and not allocated_tc_df.empty else set()
                unallocated = [c for c in st.session_state.db_employee_codes if c not in allocated_codes]

                logImport(conn, user["email"], pay_period, pay_period_start,
                          added, len(existing), unallocated)
                if unallocated:
                    with open("missing_employees.log", "a") as f:
                        f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Pay Period: {pay_period} | Missing: {', '.join(unallocated)}\n")
                st.session_state.file_uploader_key += 1

                auto_msg = f" Auto-allocated {len(auto_allocated)} salaried employee(s)." if auto_allocated else ""
                if added == 0 and existing:
                    st.session_state.import_message = ("error", f"Upload rejected: all {len(existing)} records already exist for this pay period.")
                elif existing:
                    st.session_state.import_message = ("warning", f"Imported {added} records. {len(existing)} already existed and were skipped.{auto_msg}")
                else:
                    st.session_state.import_message = ("success", f"Successfully imported {added} records.{auto_msg}")

                st.rerun()

        @st.fragment
        def export_section():
            st.markdown('<p class="sidebar-label">Export</p>', unsafe_allow_html=True)
            all_periods = getPayPeriods(conn)
            selected_periods = st.multiselect("Pay Period(s)", options=all_periods, label_visibility="collapsed")

            periods_key = tuple(sorted(selected_periods))
            if periods_key != st.session_state.get("export_periods_key"):
                st.session_state.export_periods_key = periods_key
                if selected_periods:
                    with st.spinner("Preparing export..."):
                        def to_db_period(p):
                            parts = p.split("/")
                            return f"{parts[2]}{parts[0]}{parts[1]}"
                        frames = [run_query(conn, "SELECT * FROM dbo.fn_GetExport(?)", [to_db_period(p)]) for p in selected_periods]
                        valid = [f for f in frames if f is not None and not f.empty]
                        export_df = pd.concat(valid, ignore_index=True) if valid else pd.DataFrame()
                        if not export_df.empty:
                            buf = io.BytesIO()
                            export_df.to_excel(buf, index=False)
                            st.session_state.export_bytes = buf.getvalue()
                        else:
                            st.session_state.export_bytes = None
                else:
                    st.session_state.export_bytes = None

            if selected_periods:
                if st.session_state.get("export_bytes"):
                    st.download_button("⬇️ Export to Excel", data=st.session_state.export_bytes, file_name="pars_export.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
                else:
                    st.warning("No data found for the selected pay period(s).")

        export_section()

    ctrl1, ctrl2 = st.columns([1, 1])

# ── MAIN CONTENT ──────────────────────────────────────────────────────────────
with main_col:
    match st.session_state.active_page:
        case "Timecard Allocations":
            timecard_allocations.render(conn, user, login, isAdmin=isAdmin)
        case "Approval Report Manager":
            approval_report_manager.render(conn, user, login)
        # case "Time Card Report":
        #     employee_code = login[0].employee_code
        #     managing_dept = login[0].managing_department
        #     dept_code = login[0].dept_code
        #     if not isManager:
        #         render_report(f"Invoked_x0020_function/EmployeeCode eq '{employee_code}'")
        #     else:
        #         render_report(f"Invoked_x0020_function/DepartmentCode eq '{managing_dept}' or Invoked_x0020_function/DepartmentCode eq '{dept_code}'")

# ── Sidebar resize handle ─────────────────────────────────────────────────────
components.html("""
<script>
(function() {
    function init() {
        var doc = window.parent.document;
        var sidebar = doc.querySelector(
            'div[data-testid="stHorizontalBlock"]:first-of-type > div[data-testid="stColumn"]:first-child'
        );
        var main = doc.querySelector(
            'div[data-testid="stHorizontalBlock"]:first-of-type > div[data-testid="stColumn"]:last-child'
        );
        if (!sidebar || !main) { setTimeout(init, 300); return; }
        if (doc.getElementById('sb-resize-handle')) return;

        var style = doc.createElement('style');
        style.textContent = [
            'div[data-testid="stHorizontalBlock"]:first-of-type > div[data-testid="stColumn"]:first-child { position: relative !important; }',
            '#sb-resize-handle { position:absolute; top:0; right:-3px; bottom:0; width:6px; cursor:col-resize; z-index:9998; background:transparent; }',
            '#sb-resize-handle:hover, #sb-resize-handle.dragging { background:rgba(59,130,246,0.4); border-radius:3px; }'
        ].join('');
        doc.head.appendChild(style);

        var handle = doc.createElement('div');
        handle.id = 'sb-resize-handle';
        sidebar.appendChild(handle);

        var startX, startW;
        handle.addEventListener('mousedown', function(e) {
            startX = e.clientX;
            startW = sidebar.getBoundingClientRect().width;
            handle.classList.add('dragging');
            doc.body.style.cursor = 'col-resize';
            doc.body.style.userSelect = 'none';
            e.preventDefault();
        });
        doc.addEventListener('mousemove', function(e) {
            if (!handle.classList.contains('dragging')) return;
            var w = Math.min(Math.max(startW + (e.clientX - startX), 160), 700);
            sidebar.style.minWidth = w + 'px';
            sidebar.style.maxWidth = w + 'px';
            sidebar.style.flex = '0 0 ' + w + 'px';
            if (main) {
                main.style.flex = '1 1 auto';
                main.style.minWidth = '0';
                main.style.maxWidth = 'none';
            }
        });
        doc.addEventListener('mouseup', function() {
            if (!handle.classList.contains('dragging')) return;
            handle.classList.remove('dragging');
            doc.body.style.cursor = '';
            doc.body.style.userSelect = '';
        });

        // Re-attach handle if Streamlit removes it on rerun
        new MutationObserver(function() {
            if (!doc.getElementById('sb-resize-handle')) sidebar.appendChild(handle);
        }).observe(sidebar, { childList: true });
    }
    init();
})();
</script>
""", height=0)