import streamlit as st
from Controllers.DB import *
from Controllers.timecardAllocationController import *
from Classes import *
from Jobs.notify_manager_on_acknowledge import notify_manager


def render(conn, user, login):
    st.title("Timecard Allocations")
    isManager = login[0].isManager()
    ctrl1, ctrl2, ctrl3, ctrl4 = st.columns([2, 3, 2, 2])
    
    employee_name = None  # ← initialize before columns

    with ctrl1:
        pay_period = st.selectbox(
            "Pay Period",
            options=getPayPeriods(conn),
            index=0,
        )

    with ctrl2:
        try:
            employees = getEmployeesByPayPeriod(conn, pay_period, user)
        except Exception:
            st.error("Cannot pull timecards.")
            return
        employee_name = st.selectbox(
            "Employee Name",
            options=employees,
            format_func=lambda e: e.full_name(),
        )
    approved, acknowledged = checkState(employee_name.employee_code, pay_period, conn)

    state_key = f"{employee_name.employee_code}_{pay_period}"
    if st.session_state.get("timecard_state_key") != state_key:
        st.session_state.timecard_state_key = state_key
        st.session_state.prev_approval = approved
        st.session_state.prev_acknowledged = acknowledged

    with ctrl3:
        approvalCheckbox = st.checkbox("Manager Approval", value=approved, disabled=not isManager)

    with ctrl4:
        acknowledgedCheckbox = st.checkbox("Employee Acknowledgement", value=acknowledged)

    # Only fires if the checkbox was actually toggled
    if approvalCheckbox != st.session_state.prev_approval:
        st.session_state.prev_approval = approvalCheckbox
        changeTimecardState(employee_name.employee_code, login[0].employee_code, pay_period, conn, approvalCheckbox, acknowledgedCheckbox)
        st.rerun()
    # Only fires if the checkbox was actually toggled
    if acknowledgedCheckbox != st.session_state.prev_acknowledged:
        st.session_state.prev_acknowledged = acknowledgedCheckbox
        changeTimecardState(employee_name.employee_code, login[0].employee_code, pay_period, conn, approvalCheckbox, acknowledgedCheckbox)
        if acknowledgedCheckbox:
            notify_manager(conn, employee_name.work_email, pay_period, employee_name.full_name())
        st.rerun()
    
    refresh_col, status_col , _ = st.columns([1,2,6])
    with refresh_col:
        st.button("🔄 Refresh", key="refresh_grid1")
    with status_col:
        if approved: st.success("✅ Time Card Has Been Approved")
    # Time Card Table
    if employee_name is not None:
        timecard_df = getSchedule(conn, employee_name.employee_code, pay_period)
        fund_options = getFundsByEmployee(conn, employee_name.employee_code)
        fund_allocations = getFundAllocations(conn, employee_name.work_email)
    if timecard_df.empty:
        st.caption("No records to display.")
    else:
        with st.container(border=True):

            col1, col2, col3, col4, col5, col6, col7 = st.columns([0.5, 2, 2, 1.5, 1.5, 1.5, 1.2])
            col1.markdown("&nbsp;")
            col2.markdown("**Date**")
            col3.markdown("**Pay Type**")
            col4.markdown("**Total Hours**")
            col5.markdown("**Percentage**")
            col6.markdown("<div style='text-align:center'><b>Allocations Made</b></div>", unsafe_allow_html=True)
            col7.markdown("<div style='text-align:center'><b>Fund Code Breakdown</b></div>", unsafe_allow_html=True)

            st.markdown("""
            <style>
            .fund-tooltip { position: relative; display: inline-block; cursor: help; }
            .fund-tooltip .tooltiptext {
                visibility: hidden; opacity: 0;
                background-color: #1e293b; color: #fff;
                padding: 12px 18px; border-radius: 8px;
                position: absolute; z-index: 9999;
                bottom: 130%; left: 50%; transform: translateX(-50%);
                font-size: 16px; min-width: 260px; line-height: 2;
                box-shadow: 0 4px 16px rgba(0,0,0,0.5);
                transition: opacity 0.15s;
                pointer-events: none;
            }
            .fund-tooltip:hover .tooltiptext { visibility: visible; opacity: 1; }
            </style>
            """, unsafe_allow_html=True)

            st.divider()

            task_options = getTasks(conn)

            schedule_ids = timecard_df["ScheduleID"].tolist()
            placeholders = ','.join(['?' for _ in schedule_ids])
            allocated_df = run_query(conn, f"SELECT DISTINCT ScheduleID FROM dbo.Record WHERE ScheduleID IN ({placeholders})", schedule_ids)
            allocated_ids = set(allocated_df["ScheduleID"].tolist()) if allocated_df is not None and not allocated_df.empty else set()

            for _, row in timecard_df.iterrows():

                schedule_id = row["ScheduleID"]
                key = f"expanded_{schedule_id}"
                if key not in st.session_state:
                    st.session_state[key] = False

                has_records = schedule_id in allocated_ids
                total_hours = float(row["TotalHours"])

                breakdown_html = ""
                if fund_allocations:
                    lines = [f"{f['FundCode']}: {round(total_hours * f['Percentage'] / 100, 2)}h ({f['Percentage']}%)" for f in fund_allocations]
                    breakdown_html = f'''<div style="text-align:center;"><span class="fund-tooltip">
                        <span style="font-size:20px;">ℹ️</span>
                        <span class="tooltiptext">{"<br>".join(lines)}</span>
                    </span></div>'''

                col1, col2, col3, col4, col5, col6, col7 = st.columns([0.5, 2, 2, 1.5, 1.5, 1.5, 1.2])
                with col1:
                    arrow = "▼" if st.session_state[key] else "►"
                    if st.button(arrow, key=f"btn_{schedule_id}"):
                        st.session_state[key] = not st.session_state[key]
                        st.rerun()
                col2.write(row["Date"])
                col3.write(row["PayType"])
                col4.write(row["TotalHours"])
                col5.write(f"{row['Percentage']}%")
                check_html = f'<div style="text-align:center; padding-top:4px;"><input type="checkbox" {"checked" if has_records else ""} disabled style="width:16px; height:16px; accent-color:#3b82f6; cursor:default;"></div>'
                col6.markdown(check_html, unsafe_allow_html=True)
                col7.markdown(breakdown_html, unsafe_allow_html=True)
                st.markdown("---")
                if st.session_state[key]:
                    with st.container():
                        allocations_df = getRecords(conn, schedule_id)

                        if allocations_df is None:
                            allocations_df = pd.DataFrame(columns=["ID", "Task", "Fund", "Hours"])
                        else:
                            allocations_df = allocations_df.copy()

                        editor_df = allocations_df[["ID", "Task", "Fund", "Hours"]].copy()

                        is_regular = row["PayType"] == "Regular"

                        if not is_regular:
                            st.info(f"Editing is disabled for Pay Type: **{row['PayType']}**")

                        edited_df = st.data_editor(
                            editor_df,
                            column_order=["Task", "Fund", "Hours"],
                            column_config={
                                "ID": None,
                                "Task": st.column_config.SelectboxColumn("Task", options=task_options),
                                "Fund": st.column_config.SelectboxColumn("Fund", options=fund_options),
                                "Hours": st.column_config.NumberColumn("Hours", format="%.2f"),
                            },
                            num_rows="dynamic" if is_regular else "fixed",
                            disabled=not is_regular,
                            key=f"alloc_{schedule_id}",
                        )

                        edited_df = edited_df.dropna(how="all").copy()
                        total = round(pd.to_numeric(edited_df["Hours"], errors="coerce").fillna(0).sum(), 2)
                        required = round(float(row["TotalHours"]), 2)
                        hours_match = total == required

                        st.write(f"**Total Allocation: {total:.2f}**")

                        if is_regular:
                            if not has_records and fund_allocations:
                                if st.button("Auto Allocate", key=f"auto_{schedule_id}"):
                                    auto_task = next((t for t in task_options if t.startswith("O:")), task_options[0] if task_options else "")
                                    auto_rows = []
                                    for alloc in fund_allocations:
                                        fund_option = next((f for f in fund_options if f.startswith(alloc["FundCode"] + ":")), alloc["FundCode"])
                                        hours = round(total_hours * alloc["Percentage"] / 100, 2)
                                        auto_rows.append({"ID": float("nan"), "Task": auto_task, "Fund": fund_option, "Hours": hours})
                                    auto_df = pd.DataFrame(auto_rows, columns=["ID", "Task", "Fund", "Hours"])
                                    saveAllocations(conn, schedule_id, auto_df)
                                    st.success("✅ Auto-allocated successfully!")
                                    st.rerun()

                            if not hours_match:
                                st.error("Allocated Hours Must Equate To Total Hours")

                            if hours_match and st.button(
                                "💾 Save Allocations",
                                key=f"save_{schedule_id}",
                            ):
                                original_ids = set(allocations_df["ID"].dropna().astype(int))
                                edited_ids = set(edited_df["ID"].dropna().astype(int))
                                deleted_ids = original_ids - edited_ids

                                for deleted_id in deleted_ids:
                                    deleteRecord(conn, int(deleted_id))

                                saveAllocations(conn, schedule_id, edited_df)
                                st.success("✅ Saved successfully!")  
                            