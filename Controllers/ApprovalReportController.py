from Controllers.DB import *


def getApprovalsByPayPeriod(conn, pay_period, login):
    """
    Retrieves the detailed approval report for the logged-in manager's department
    for a given pay period.

    The pay period is expected in MM/DD/YYYY format as supplied by the UI and is
    converted to YYYYMMDD internally before being passed to fn_DetailedApprovalReport.
    Results are scoped to the manager's email so each manager only sees their own department.

    Args:
        conn (pyodbc.Connection): An active database connection.
        pay_period (str): The pay period end date in MM/DD/YYYY format.
        login (list[Employee]): The current session's login object; login[0] provides the manager's email.

    Returns:
        pd.DataFrame: All approval report rows for the manager's department in the specified period.
    """
    parts = pay_period.split("/")
    period = f"{parts[2]}{parts[0]}{parts[1]}"
    return run_query(conn, """
        SELECT * FROM dbo.fn_DetailedApprovalReport(?, ?);
    """, [login[0].work_email, period])
