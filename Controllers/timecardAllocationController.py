import pandas as pd
import pyodbc
from datetime import datetime
from Classes import *
from Controllers.DB import * 

def getPayPeriods(conn):
    """
    Get a list of all available pay periods from the db 
    """
    payPeriods = run_query(conn, """
        SELECT DISTINCT PayPeriod FROM Time_Card ORDER BY PayPeriod ASC
    """)["PayPeriod"].astype(str).tolist()
    
    formatted_dates = [f"{d[4:6]}/{d[6:8]}/{d[0:4]}" for d in payPeriods]
    return formatted_dates
     
def importTimeCards(df, conn):
    """
    Function to handle the importing of time cards and allocation to the db 
    """

    # For Tracking existing schedules - shouldnt really happen 
    existing_records = []

    # Add Date column to df BEFORE grouping
    df["Date"] = pd.to_datetime(df["OutPunchTime"], errors='coerce').dt.normalize()

    # Get max date per employee
    max_dates = df.groupby("EECode")["Date"].max()
    
    # Create one time card per employee
    for employeecode, max_date in max_dates.items():
        max_date_str = max_date.strftime('%Y%m%d')
        timeCardID = f"TCARD{employeecode}{max_date_str}"

        timeCardExisting = run_query(conn, """
            SELECT * FROM dbo.Time_Card WHERE TimeCardID = ?
        """, [timeCardID])

        if timeCardExisting.empty:
            createTimeCard(max_date_str, employeecode, timeCardID, 0, conn)

    # Group by Employee Code AND Date
    groups = df.groupby(["EECode", "Date"])

    for (employeecode, date), groupdf in groups:
        # Determine total hours for the day
        total_hours = groupdf["EarnHours"].sum()

        #Total Hours Is Dependent on the allocated amount per day per employee not a base set of 7 

        hoursAllowed = run_query(conn, """
        Select PayPeriodHours From EmployeeInformation Where EmployeeCode = ? 
        """, [employeecode]).iloc[0][0]
        if total_hours == 0 : total_hours = 7
        # Create the Schedule ID e.g. SCHA0LF20251207
        schedualID = f"SCH{employeecode}{date.strftime('%Y%m%d')}"

        # Determine percentage of the day
        percentage = round((total_hours / hoursAllowed) * 100, 2)

        # Get timeCardID from max_dates
        timeCardID = f"TCARD{employeecode}{max_dates[employeecode].strftime('%Y%m%d')}"

        # Check if schedule record already exists
        schedule_existing = run_query(conn, """
            SELECT * FROM dbo.Schedule WHERE ScheduleID = ?
        """, [schedualID])
        earn_code = groupdf["EarnCode"].iloc[0]
        pay_type = "Regular" if pd.isna(earn_code) else earn_code
        print(pay_type)
        if(pay_type != "Regular"):
            df = run_query(conn, """
            SELECT Typedesc FROM dbo.PaycomEarnCodes WHERE Typecode = ?
            """, [pay_type])
            pay_type = (df.iloc[0][0])
        
        if not schedule_existing.empty:
            existing_records.append(schedualID)
            continue

        run_query(conn, """
            INSERT INTO dbo.Schedule (ScheduleID, EmployeeCode, Date, PayType, TotalHours, Percentage, TimeCardID)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [schedualID, employeecode, date.strftime('%Y%m%d'), str(pay_type), total_hours, percentage, timeCardID])

    return existing_records


def createTimeCard(payPeriod, EmployeeCode, TimeCardID, Approved, conn):
    """
    Make an unexisting time card
    """

    return run_query(
        conn, """
    INSERT INTO dbo.Time_Card (TimeCardID, EmployeeCode, PayPeriod, Approval)
    VALUES (?,?,?,?)
    """, [TimeCardID, EmployeeCode, payPeriod, Approved]
              )


def getSchedule(conn, EmployeeCode, PayPeriod):
    parts = PayPeriod.split("/")
    period = f"{parts[2]}{parts[0]}{parts[1]}"
    
    return run_query(conn, """
        SELECT S.ScheduleID, S.EmployeeCode, S.Date, S.PayType, 
               S.TotalHours, S.Percentage, T.PayPeriod
        FROM Schedule AS S 
        LEFT JOIN Time_Card AS T ON T.TimeCardID = S.TimeCardID 
        WHERE S.EmployeeCode = ? AND T.PayPeriod = ?
    """, [EmployeeCode, period])
    

def getEmployeesByPayPeriod(conn, pay_period, user):
    """
    Get employees that have time cards for a given pay period
    """

    #Determine The Employees that are under an individual
    parts = pay_period.split("/")
    period = f"{parts[2]}{parts[0]}{parts[1]}"
    
    df = run_query(conn, """
        SELECT * FROM dbo.fn_GetEmployeesByManagerEmail(?, ?);
    """, [user['email'], period])
    return [Employee(
        row["EmployeeCode"],
        row["EmployeeLast"],
        row["EmployeeFirst"],
        row["DepartmentCode"],
        row["WorkEmail"],
        "N/A",
        row["PayPeriodHours"]
    ) for _, row in df.iterrows()]


def getRecords(conn, schedule_id):
    return run_query(conn, """
        SELECT Task, Fund, Hours, ID 
        FROM dbo.Record
        WHERE ScheduleID = ?
    """, [schedule_id])


def getTasks(conn):
    df =  run_query(conn, "SELECT Code, Description FROM dbo.[Activities]")
    return (df["Code"] + ":" + df["Description"]).tolist()

def getFundsByEmployee(conn, employee_code):
    df = run_query(conn, """
        SELECT DISTINCT F.FundCode, F.FundDescription 
        FROM Funds AS F 
        LEFT JOIN EmployeeFundMatch AS E ON F.FundCode = E.Fund_Code 
        WHERE E.EE_Code = ?
    """, [employee_code])
    return (df["FundCode"] + ":" + df["FundDescription"]).tolist()

def saveAllocations(conn, schedule_id, edited_df):
    """
    Save records for a schedule.
    Inserts rows with no ID, updates rows that already have an ID.
    """
    records_size = run_query(
        conn,
        "SELECT COUNT(*) AS count FROM dbo.Record"
    ).iloc[0, 0]

    edited_df = edited_df.dropna(how="all").copy()
    edited_df["Hours"] = pd.to_numeric(edited_df["Hours"], errors="coerce")

    for idx, row in edited_df.iterrows():
        pct = row["Hours"]

        if pd.isna(pct):
            
            continue

        if pd.isna(row["ID"]) or row["ID"] == "":
            new_id = records_size + idx + 1
            edited_df.at[idx, "ID"] = new_id

            run_query(
                conn,
                """
                INSERT INTO dbo.Record (Task, Fund, Hours, ID, ScheduleID)
                VALUES (?,?,?,?,?)
                """,
                [str(row["Task"]), str(row["Fund"]), float(pct), int(new_id), str(schedule_id)]
            )
        else:
            run_query(
                conn,
                """
                UPDATE dbo.Record
                SET Task = ?,
                    Fund = ?,
                    Hours = ?,
                    ScheduleID = ?
                WHERE ID = ?
                """,
                [str(row["Task"]), str(row["Fund"]), float(pct), str(schedule_id), int(row["ID"])]
            )

    return edited_df

def deleteRecord(conn, recordID): 
    """
    Delete A Task Record From The DB 
    """
    
    run_query(
        conn,
        "DELETE FROM Record WHERE ID LIKE ?",
        [f"%{recordID}%"]
    )

def changeTimecardState(emplyeeCode, approverCode,  payPeriod, conn, approval, acknowledged):
    #Determine The Employees that are under an individual
    parts = payPeriod.split("/")
    period = f"{parts[2]}{parts[0]}{parts[1]}"
    timeCardID = f'TCARD{emplyeeCode}{period}'
    today = datetime.today().strftime('%Y-%m-%d') 
    run_query(conn, """
    UPDATE Time_Card
    SET Approval = ? , ApprovedBy = ? , ApprovedDate = ? , Acknowledged = ? , AcknowledgedDate = ? 
    WHERE TimeCardID = ?
    """,[approval,approverCode , today , acknowledged, today ,timeCardID]
              )

def checkState(employeeCode, payPeriod, conn):
    parts = payPeriod.split("/")
    period = f"{parts[2]}{parts[0]}{parts[1]}"
    timeCardID = f'TCARD{employeeCode}{period}'

    df = run_query(conn, """
        SELECT Approval, Acknowledged 
        FROM Time_Card 
        WHERE TimeCardID = ?
    """, [timeCardID])

    if df is None or df.empty:
        return (0, 0)

    approval    = int(df.iloc[0, 0]) if pd.notna(df.iloc[0, 0]) else 0
    acknowledged = int(df.iloc[0, 1]) if pd.notna(df.iloc[0, 1]) else 0

    return (approval, acknowledged)
