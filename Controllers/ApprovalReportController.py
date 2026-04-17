from Controllers.DB import * 

def getApprovalsByPayPeriod(conn, pay_period, login):
    """
    Get employees that have time cards for a given pay period
    """

    #Determine The Employees that are under an individual
    parts = pay_period.split("/")
    period = f"{parts[2]}{parts[0]}{parts[1]}"
    
    df = run_query(conn, """
        SELECT * FROM dbo.fn_DetailedApprovalReport(?, ?);
    """, [login[0].work_email, period])
    return df