from Controllers.DB import *


def getApprovalsByPayPeriod(conn, pay_period, login):
    parts = pay_period.split("/")
    period = f"{parts[2]}{parts[0]}{parts[1]}"
    return run_query(conn, """
        SELECT * FROM dbo.fn_DetailedApprovalReport(?, ?);
    """, [login[0].work_email, period])
