import streamlit as st
from Controllers.DB import *
from Controllers.timecardAllocationController import * 
from Classes import * 
def render(conn, user, login):
    st.title("Timecard Allocations")
    # Controls Row
    
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
        employees = getEmployeesByPayPeriod(conn, pay_period, user)
        employee_name = st.selectbox(
            "Employee Name",
            options=employees,
            format_func=lambda e: e.full_name(),
        )
    approved , acknowledged   = checkState(employee_name.employee_code, pay_period, conn)
    
    with ctrl3:
        if "prev_approval" not in st.session_state:
            st.session_state.prev_approval = approved  # set to DB value on load

        approvalCheckbox = st.checkbox("Manager Approval", value=approved, disabled=not isManager)

    with ctrl4:
        if "prev_acknowledged" not in st.session_state:
            st.session_state.prev_acknowledged = acknowledged  # set to DB value on load

        acknowledgedCheckbox = st.checkbox("Employee Acknowledgement", value=acknowledged)

        
    # Only fires if the checkbox was actually toggled
    if approvalCheckbox != st.session_state.prev_approval:
        st.session_state.prev_approval = approvalCheckbox
        changeTimecardState(employee_name.employee_code, login[0].employee_code, pay_period, conn, approvalCheckbox , acknowledgedCheckbox)
        st.rerun()   
    # Only fires if the checkbox was actually toggled
    if acknowledgedCheckbox != st.session_state.prev_acknowledged:
        st.session_state.prev_acknowledged = acknowledgedCheckbox
        changeTimecardState(employee_name.employee_code, login[0].employee_code, pay_period, conn, approvalCheckbox , acknowledgedCheckbox)
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

    if timecard_df.empty:
        st.caption("No records to display.")
    else:
        with st.container(border=True):

            col1, col2, col3, col4, col5 = st.columns([0.5, 2, 2, 1.5, 1.5])
            col1.markdown("&nbsp;")
            col2.markdown("**Date**")
            col3.markdown("**Pay Type**")
            col4.markdown("**Total Hours**")
            col5.markdown("**Percentage**")

            st.divider()

            task_options = getTasks(conn)

            for _, row in timecard_df.iterrows():
                
                schedule_id = row["ScheduleID"]
                key = f"expanded_{schedule_id}"

                if key not in st.session_state:
                    st.session_state[key] = False

                col1, col2, col3, col4, col5 = st.columns([0.5, 2, 2, 1.5, 1.5])
                with col1:
                    arrow = "▼" if st.session_state[key] else "►"
                    if st.button(arrow, key=f"btn_{schedule_id}"):
                        st.session_state[key] = not st.session_state[key]
                        st.rerun()
                #This is for testing purposes
                #second change for kg
                col2.write(row["Date"])
                col3.write(row["PayType"])
                col4.write(row["TotalHours"])
                col5.write(f"{row['Percentage']}%")
                st.markdown("---")
                if st.session_state[key]:
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
                            key=f"alloc_{schedule_id}",
                        )

                        edited_df = edited_df.dropna(how="all").copy()
                        total = pd.to_numeric(edited_df["Hours"], errors="coerce").fillna(0).sum()

                        st.write(f"**Total Allocation: {total:.2f}**")

                        if total != float(row["TotalHours"]):
                            st.error("Allocated Hours Must Equate To Total Hours")

                        if st.button(
                            "💾 Save Allocations",
                            key=f"save_{schedule_id}",
                            disabled=total > float(row["TotalHours"]),
                        ):
                            original_ids = set(allocations_df["ID"].dropna().astype(int))
                            edited_ids = set(edited_df["ID"].dropna().astype(int))
                            deleted_ids = original_ids - edited_ids

                            for deleted_id in deleted_ids:
                                deleteRecord(conn, int(deleted_id))

                            saveAllocations(conn, schedule_id, edited_df)
                            st.success("✅ Saved successfully!")  
                            