import streamlit as st
from Controllers.timecardAllocationController import getPayPeriods , getEmployeesByPayPeriod
from Controllers.ApprovalReportController import * 
def render(conn, user, login : Employee):
    st.title("Approval Report Manager")
    

    ctrl1, _ = st.columns([2, 5])

    with ctrl1:
        pay_period = st.selectbox(
            "Pay Period",
            options=getPayPeriods(conn),
            index=0,
        )
    with st.container(border=True, key="ApprovalReportManagerTableContainer"):
        employees = getApprovalsByPayPeriod(conn, pay_period, login)
        st.dataframe(employees)
