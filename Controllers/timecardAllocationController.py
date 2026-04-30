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
    existing_records = []
    missing_employees = []

    df["Date"] = pd.to_datetime(df["OutPunchTime"], errors='coerce').dt.normalize()
    max_date = df["Date"].max()
    min_date = df["Date"].min()

    # Always generate exactly 10 days for the pay period
    pay_period_dates = pd.date_range(start=min_date, periods=10, freq='D')

    # Create one time card per employee
    for employeecode in df["EECode"].unique():
        employeecode = str(employeecode).strip()
        max_date_str = max_date.strftime('%Y%m%d')
        min_date_str = min_date.strftime('%Y%m%d')
        timeCardID = f"TCARD{employeecode}{max_date_str}"
        timeCardExisting = run_query(conn, """
            SELECT * FROM dbo.Time_Card WHERE TimeCardID = ?
        """, [timeCardID])
        if timeCardExisting.empty:
            createTimeCard(max_date_str, employeecode, timeCardID, 0, min_date_str, conn)

    # Track every (employeecode, date) that gets processed from real punch data
    processed = set()

    day_groups = df.groupby(["EECode", "Date"])
    for (employeecode, date), daydf in day_groups:
        employeecode = str(employeecode).strip()
        processed.add((employeecode, date))

        hours_result = run_query(conn, """
            Select PayPeriodHours From EmployeeInformation Where EmployeeCode = ?
        """, [employeecode])
        try:
            if hours_result is None or hours_result.empty:
                missing_employees.append(employeecode)
                continue
            hoursAllowed = hours_result.iloc[0, 0]
            if pd.isna(hoursAllowed) or hoursAllowed == 0:
                missing_employees.append(employeecode)
                continue
        except Exception as e:
            missing_employees.append(employeecode)
            continue

        timeCardID = f"TCARD{employeecode}{max_date.strftime('%Y%m%d')}"

        non_regular = daydf[daydf["EarnCode"].notna() & (daydf["EarnCode"] != "")]
        non_regular_hours = non_regular["EarnHours"].sum()

        for earn_code, earn_group in non_regular.groupby("EarnCode"):
            earn_code = str(earn_code).strip()
            earn_hours = earn_group["EarnHours"].sum()

            pay_df = run_query(conn, """
                SELECT Typedesc FROM dbo.PaycomEarnCodes WHERE Typecode = ?
            """, [earn_code])
            pay_type = pay_df.iloc[0, 0] if not pay_df.empty else earn_code

            schedualID = f"SCH{employeecode}{date.strftime('%Y%m%d')}{earn_code}"
            percentage = round((earn_hours / hoursAllowed) * 100, 2)

            schedule_existing = run_query(conn, """
                SELECT * FROM dbo.Schedule WHERE ScheduleID = ?
            """, [schedualID])
            if not schedule_existing.empty:
                existing_records.append(schedualID)
                continue

            run_query(conn, """
                INSERT INTO dbo.Schedule (ScheduleID, EmployeeCode, Date, PayType, TotalHours, Percentage, TimeCardID)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, [schedualID, employeecode, date.strftime('%Y%m%d'), str(pay_type), earn_hours, percentage, timeCardID])

        regular_hours = daydf["EarnHours"].sum() - non_regular_hours
        if regular_hours <= 0:
            regular_hours = hoursAllowed - non_regular_hours
        if regular_hours <= 0:
            continue

        schedualID = f"SCH{employeecode}{date.strftime('%Y%m%d')}REG"
        percentage = round((regular_hours / hoursAllowed) * 100, 2)

        schedule_existing = run_query(conn, """
            SELECT * FROM dbo.Schedule WHERE ScheduleID = ?
        """, [schedualID])
        if not schedule_existing.empty:
            existing_records.append(schedualID)
            continue

        run_query(conn, """
            INSERT INTO dbo.Schedule (ScheduleID, EmployeeCode, Date, PayType, TotalHours, Percentage, TimeCardID)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [schedualID, employeecode, date.strftime('%Y%m%d'), 'Regular', regular_hours, percentage, timeCardID])

    # --- Backfill any missing days across the full 10-day pay period ---
    for employeecode in df["EECode"].unique():
        employeecode = str(employeecode).strip()

        hours_result = run_query(conn, """
            Select PayPeriodHours From EmployeeInformation Where EmployeeCode = ?
        """, [employeecode])
        try:
            if hours_result is None or hours_result.empty:
                continue
            hoursAllowed = hours_result.iloc[0, 0]
            if pd.isna(hoursAllowed) or hoursAllowed == 0:
                continue
        except Exception:
            continue

        timeCardID = f"TCARD{employeecode}{max_date.strftime('%Y%m%d')}"

        for date in pay_period_dates:
            if (employeecode, date) in processed:
                continue  # Already handled with real punch data above

            schedualID = f"SCH{employeecode}{date.strftime('%Y%m%d')}REG"

            schedule_existing = run_query(conn, """
                SELECT * FROM dbo.Schedule WHERE ScheduleID = ?
            """, [schedualID])
            if not schedule_existing.empty:
                existing_records.append(schedualID)
                continue

            # No punch data for this day — insert full allocated hours as Regular
            run_query(conn, """
                INSERT INTO dbo.Schedule (ScheduleID, EmployeeCode, Date, PayType, TotalHours, Percentage, TimeCardID)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, [schedualID, employeecode, date.strftime('%Y%m%d'), 'Regular', hoursAllowed, 100.0, timeCardID])

    if missing_employees:
        print(f"Missing employees not found in EmployeeInformation: {list(set(missing_employees))}")

    return existing_records, missing_employees


def createTimeCard(payPeriod, EmployeeCode, TimeCardID, Approved, MinDate,conn):
    """
    Make an unexisting time card
    """

    return run_query(
        conn, """
    INSERT INTO dbo.Time_Card (TimeCardID, EmployeeCode, PayPeriod, Approval, PayPeriodStart)
    VALUES (?,?,?,?,?)
    """, [TimeCardID, EmployeeCode, payPeriod, Approved,MinDate]
              )


def getSchedule(conn, EmployeeCode, PayPeriod):
    parts = PayPeriod.split("/")
    period = f"{parts[2]}{parts[0]}{parts[1]}"
    
    return run_query(conn, """
        SELECT S.ScheduleID, S.EmployeeCode, S.Date, S.PayType, 
               S.TotalHours, S.Percentage, T.PayPeriod
        FROM Schedule AS S 
        LEFT JOIN Time_Card AS T ON T.TimeCardID = S.TimeCardID 
        WHERE S.EmployeeCode = ? AND T.PayPeriod = ? Order By S.Date ASC
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
