import pandas as pd
from datetime import datetime
from Classes import *
from Controllers.DB import *


def getPayPeriods(conn):
    """
    Retrieves all distinct pay periods from the Time_Card table, formatted for display in the UI.

    Pay periods are stored as YYYYMMDD integers in the database and are converted to
    MM/DD/YYYY strings on the way out for use in Streamlit selectbox components.

    Args:
        conn (pyodbc.Connection): An active database connection.

    Returns:
        list[str]: A list of pay period strings in MM/DD/YYYY format, ordered ascending.
    """
    payPeriods = run_query(conn, """
        SELECT DISTINCT PayPeriod FROM Time_Card ORDER BY PayPeriod ASC
    """)["PayPeriod"].astype(str).tolist()
    return [f"{d[4:6]}/{d[6:8]}/{d[0:4]}" for d in payPeriods]


def importTimeCards(df, conn):
    """
    Processes a timecard export DataFrame and persists the results to the Schedule and Time_Card tables.

    The pay period is determined automatically by matching the maximum date in the file against
    vw_PayPeriods. If a match is found, the DB-defined period boundaries are used; otherwise the
    file's own date range is used as a fallback.

    For each employee and date combination, non-regular earn codes (e.g. OT, sick) are inserted
    as separate Schedule entries. Regular hours are calculated as the remainder and inserted as a
    Regular entry. After processing all punched days, any weekday within the pay period that had
    no punch data is backfilled with a full Regular day at the employee's standard PayPeriodHours.

    Employees not found in EmployeeInformation or with zero PayPeriodHours are flagged as missing
    and excluded from the import. Records that already exist in the Schedule table are skipped and
    tracked separately.

    Args:
        df (pd.DataFrame): A DataFrame parsed from the uploaded Excel file. Must contain
                           EECode, OutPunchTime, EarnHours, and EarnCode columns.
        conn (pyodbc.Connection): An active database connection.

    Returns:
        tuple: (existing_records, missing_employees, records_added, pay_period_str, pay_period_start_str)
            - existing_records (list[str]): Schedule IDs that were skipped because they already exist.
            - missing_employees (list[str]): Employee codes not found in EmployeeInformation.
            - records_added (int): Number of new Schedule rows successfully inserted.
            - pay_period_str (str): The resolved pay period end date in YYYYMMDD format.
            - pay_period_start_str (str): The resolved pay period start date in YYYYMMDD format.
    """
    existing_records = []
    missing_employees = []
    records_added = 0

    df["Date"] = pd.to_datetime(df["InPunchTime"], errors='coerce').dt.normalize()
    max_date = df["Date"].max()
    min_date = df["Date"].min()

    period_match = run_query(conn, """
        SELECT PayPeriod, PayPeriodStart
        FROM dbo.vw_PayPeriods
        WHERE ? > PayPeriodStart AND ? <= PayPeriod
    """, [max_date.strftime('%Y%m%d'), max_date.strftime('%Y%m%d')])

    if not period_match.empty:
        max_date = pd.to_datetime(str(period_match.iloc[0]["PayPeriod"]), format='%Y%m%d')
        min_date = pd.to_datetime(str(period_match.iloc[0]["PayPeriodStart"]), format='%Y%m%d')

    pay_period_dates = pd.date_range(start=min_date, periods=10, freq='B')
    max_date_str = max_date.strftime('%Y%m%d')
    min_date_str = min_date.strftime('%Y%m%d')

    employee_codes = [str(c).strip() for c in df["EECode"].unique()]

    # Bulk fetch PayPeriodHours for all employees in one query
    placeholders = ','.join(['?' for _ in employee_codes])
    hours_df = run_query(conn, f"SELECT EmployeeCode, PayPeriodHours FROM dbo.vw_EmployeeInformation WHERE EmployeeCode IN ({placeholders})", employee_codes)
    hours_map = {}
    if hours_df is not None and not hours_df.empty:
        hours_map = {str(r["EmployeeCode"]).strip(): r["PayPeriodHours"] for _, r in hours_df.iterrows()}

    # Bulk fetch all earn code descriptions in one query
    earn_df = run_query(conn, "SELECT Typecode, Typedesc FROM dbo.PaycomEarnCodes")
    earn_code_map = {}
    if earn_df is not None and not earn_df.empty:
        earn_code_map = {str(r["Typecode"]).strip(): r["Typedesc"] for _, r in earn_df.iterrows()}

    # Bulk fetch existing TimeCards for this pay period
    existing_tc_df = run_query(conn, "SELECT TimeCardID FROM dbo.Time_Card WHERE PayPeriod = ?", [max_date_str])
    existing_timecards = set(existing_tc_df["TimeCardID"].tolist()) if existing_tc_df is not None and not existing_tc_df.empty else set()

    # Bulk fetch existing ScheduleIDs for this pay period
    existing_sched_df = run_query(conn, """
        SELECT S.ScheduleID FROM dbo.Schedule S
        JOIN dbo.Time_Card T ON S.TimeCardID = T.TimeCardID
        WHERE T.PayPeriod = ?
    """, [max_date_str])
    existing_schedule_ids = set(existing_sched_df["ScheduleID"].tolist()) if existing_sched_df is not None and not existing_sched_df.empty else set()

    # Batch insert any missing TimeCards
    new_timecards = [
        (f"TCARD{ec}{max_date_str}", ec, max_date_str, 0, min_date_str)
        for ec in employee_codes
        if ec in hours_map and f"TCARD{ec}{max_date_str}" not in existing_timecards
    ]
    if new_timecards:
        cursor = conn.cursor()
        cursor.executemany(
            "INSERT INTO dbo.Time_Card (TimeCardID, EmployeeCode, PayPeriod, Approval, PayPeriodStart) VALUES (?, ?, ?, ?, ?)",
            new_timecards
        )
        conn.commit()

    processed = set()
    schedule_rows = []

    for (employeecode, date), daydf in df.groupby(["EECode", "Date"]):
        employeecode = str(employeecode).strip()
        processed.add((employeecode, date))

        hoursAllowed = hours_map.get(employeecode)
        if hoursAllowed is None or pd.isna(hoursAllowed) or hoursAllowed == 0:
            continue

        timeCardID = f"TCARD{employeecode}{max_date_str}"
        non_regular = daydf[daydf["EarnCode"].notna() & (daydf["EarnCode"] != "")]
        non_regular_hours = non_regular["EarnHours"].sum()

        for earn_code, earn_group in non_regular.groupby("EarnCode"):
            earn_code = str(earn_code).strip()
            earn_hours = earn_group["EarnHours"].sum()
            pay_type = earn_code_map.get(earn_code, earn_code)
            schedualID = f"SCH{employeecode}{date.strftime('%Y%m%d')}{earn_code}"
            percentage = round((earn_hours / hoursAllowed) * 100, 2)

            if schedualID in existing_schedule_ids:
                existing_records.append(schedualID)
                continue

            schedule_rows.append((schedualID, employeecode, date.strftime('%Y%m%d'), str(pay_type), earn_hours, percentage, timeCardID))
            existing_schedule_ids.add(schedualID)
            records_added += 1

        regular_hours = daydf["EarnHours"].sum() - non_regular_hours
        if regular_hours <= 0:
            regular_hours = hoursAllowed - non_regular_hours
        if regular_hours <= 0:
            continue

        schedualID = f"SCH{employeecode}{date.strftime('%Y%m%d')}REG"
        percentage = round((regular_hours / hoursAllowed) * 100, 2)

        if schedualID in existing_schedule_ids:
            existing_records.append(schedualID)
            continue

        schedule_rows.append((schedualID, employeecode, date.strftime('%Y%m%d'), 'Regular', regular_hours, percentage, timeCardID))
        existing_schedule_ids.add(schedualID)
        records_added += 1

    # Backfill weekdays with no punch data across the full pay period
    for employeecode in employee_codes:
        hoursAllowed = hours_map.get(employeecode)
        if hoursAllowed is None or pd.isna(hoursAllowed) or hoursAllowed == 0:
            continue

        timeCardID = f"TCARD{employeecode}{max_date_str}"

        for date in pay_period_dates:
            if (employeecode, date) in processed:
                continue

            schedualID = f"SCH{employeecode}{date.strftime('%Y%m%d')}REG"

            if schedualID in existing_schedule_ids:
                existing_records.append(schedualID)
                continue

            schedule_rows.append((schedualID, employeecode, date.strftime('%Y%m%d'), 'Regular', hoursAllowed, 100.0, timeCardID))
            existing_schedule_ids.add(schedualID)
            records_added += 1

    # Batch insert all Schedule records in one round-trip
    if schedule_rows:
        cursor = conn.cursor()
        cursor.executemany(
            "INSERT INTO dbo.Schedule (ScheduleID, EmployeeCode, Date, PayType, TotalHours, Percentage, TimeCardID) VALUES (?, ?, ?, ?, ?, ?, ?)",
            schedule_rows
        )
        conn.commit()

    return existing_records, missing_employees, records_added, max_date_str, min_date_str


def autoAllocateSalariedEmployees(conn, pay_period_str, pay_period_start_str, employee_codes):
    """
    Ensures every provided salaried employee has a complete Regular schedule for the given pay period.

    Called after each import to cover employees who were absent from the uploaded file. For each
    employee code provided, the function checks whether a full set of 10 business day Regular
    Schedule entries already exists for the pay period. If so, the employee is skipped entirely.
    Otherwise, a Time_Card is created if one does not exist, and any missing business day entries
    are inserted as Regular records at the employee's standard PayPeriodHours with 100% allocation.

    Employees without a record in EmployeeInformation or with PayPeriodHours of zero are skipped.

    Args:
        conn (pyodbc.Connection): An active database connection.
        pay_period_str (str): The pay period end date in YYYYMMDD format.
        pay_period_start_str (str): The pay period start date in YYYYMMDD format.
        employee_codes (list[str]): Employee codes to evaluate for auto-allocation.

    Returns:
        list[str]: Employee codes for which at least one new Schedule row was inserted.
    """
    pay_period_dates = pd.date_range(
        start=pd.to_datetime(pay_period_start_str, format='%Y%m%d'),
        periods=10, freq='B'
    )
    auto_allocated = []

    if not employee_codes:
        return auto_allocated

    placeholders = ','.join(['?' for _ in employee_codes])
    hours_df = run_query(conn, f"SELECT EmployeeCode, PayPeriodHours FROM dbo.vw_EmployeeInformation WHERE EmployeeCode IN ({placeholders})", employee_codes)
    hours_map = {str(r["EmployeeCode"]).strip(): r["PayPeriodHours"] for _, r in hours_df.iterrows()} if hours_df is not None and not hours_df.empty else {}

    existing_reg_df = run_query(conn, f"""
        SELECT S.EmployeeCode, COUNT(*) AS cnt
        FROM dbo.Schedule S
        JOIN dbo.Time_Card T ON T.TimeCardID = S.TimeCardID
        WHERE S.EmployeeCode IN ({placeholders}) AND T.PayPeriod = ? AND S.PayType = 'Regular'
        GROUP BY S.EmployeeCode
    """, employee_codes + [pay_period_str])
    existing_reg_map = {str(r["EmployeeCode"]).strip(): r["cnt"] for _, r in existing_reg_df.iterrows()} if existing_reg_df is not None and not existing_reg_df.empty else {}

    existing_tc_df = run_query(conn, f"""
        SELECT TimeCardID FROM dbo.Time_Card
        WHERE EmployeeCode IN ({placeholders}) AND PayPeriod = ?
    """, employee_codes + [pay_period_str])
    existing_timecards = set(existing_tc_df["TimeCardID"].tolist()) if existing_tc_df is not None and not existing_tc_df.empty else set()

    existing_sched_df = run_query(conn, f"""
        SELECT S.ScheduleID FROM dbo.Schedule S
        JOIN dbo.Time_Card T ON T.TimeCardID = S.TimeCardID
        WHERE S.EmployeeCode IN ({placeholders}) AND T.PayPeriod = ? AND S.PayType = 'Regular'
    """, employee_codes + [pay_period_str])
    existing_schedule_ids = set(existing_sched_df["ScheduleID"].tolist()) if existing_sched_df is not None and not existing_sched_df.empty else set()

    new_timecards = []
    schedule_rows = []

    for employeecode in employee_codes:
        existing_count = existing_reg_map.get(employeecode, 0)
        if existing_count >= len(pay_period_dates):
            continue

        hoursAllowed = hours_map.get(employeecode)
        if hoursAllowed is None or pd.isna(hoursAllowed) or hoursAllowed == 0:
            continue

        timeCardID = f"TCARD{employeecode}{pay_period_str}"
        if timeCardID not in existing_timecards:
            new_timecards.append((timeCardID, employeecode, pay_period_str, 0, pay_period_start_str))
            existing_timecards.add(timeCardID)

        days_inserted = 0
        for date in pay_period_dates:
            schedualID = f"SCH{employeecode}{date.strftime('%Y%m%d')}REG"
            if schedualID in existing_schedule_ids:
                continue
            schedule_rows.append((schedualID, employeecode, date.strftime('%Y%m%d'), 'Regular', hoursAllowed, 100.0, timeCardID))
            existing_schedule_ids.add(schedualID)
            days_inserted += 1

        if days_inserted > 0:
            auto_allocated.append(employeecode)

    if new_timecards:
        cursor = conn.cursor()
        cursor.executemany(
            "INSERT INTO dbo.Time_Card (TimeCardID, EmployeeCode, PayPeriod, Approval, PayPeriodStart) VALUES (?, ?, ?, ?, ?)",
            new_timecards
        )
        conn.commit()

    if schedule_rows:
        cursor = conn.cursor()
        cursor.executemany(
            "INSERT INTO dbo.Schedule (ScheduleID, EmployeeCode, Date, PayType, TotalHours, Percentage, TimeCardID) VALUES (?, ?, ?, ?, ?, ?, ?)",
            schedule_rows
        )
        conn.commit()

    return auto_allocated


def createTimeCard(payPeriod, EmployeeCode, TimeCardID, Approved, MinDate, conn):
    """
    Inserts a new Time_Card record into the database.

    The TimeCardID is expected to follow the convention TCARD{EmployeeCode}{YYYYMMDD},
    making it directly derivable without requiring a separate lookup. Approval is
    typically initialized to 0 and updated later through the approval workflow.

    Args:
        payPeriod (str): The pay period end date in YYYYMMDD format.
        EmployeeCode (str): The employee's unique identifier.
        TimeCardID (str): The constructed Time_Card primary key.
        Approved (int): Initial approval state; 0 for unapproved, 1 for approved.
        MinDate (str): The pay period start date in YYYYMMDD format.
        conn (pyodbc.Connection): An active database connection.

    Returns:
        None
    """
    return run_query(conn, """
        INSERT INTO dbo.Time_Card (TimeCardID, EmployeeCode, PayPeriod, Approval, PayPeriodStart)
        VALUES (?, ?, ?, ?, ?)
    """, [TimeCardID, EmployeeCode, payPeriod, Approved, MinDate])


def getSchedule(conn, EmployeeCode, PayPeriod):
    """
    Retrieves all Schedule entries for a given employee and pay period, ordered by date ascending.

    The pay period is accepted in MM/DD/YYYY format as provided by the UI and is converted
    to YYYYMMDD internally before querying. Joins against Time_Card to filter by pay period.

    Args:
        conn (pyodbc.Connection): An active database connection.
        EmployeeCode (str): The employee's unique identifier.
        PayPeriod (str): The pay period end date in MM/DD/YYYY format.

    Returns:
        pd.DataFrame: Schedule rows including ScheduleID, Date, PayType, TotalHours, Percentage, and PayPeriod.
    """
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
    Retrieves the list of employees accessible to the logged-in user for a given pay period.

    Delegates to fn_GetEmployeesByManagerEmail, which scopes results to the manager's department.
    Non-manager employees will only see themselves. The pay period is converted from MM/DD/YYYY
    to YYYYMMDD before the query.

    Args:
        conn (pyodbc.Connection): An active database connection.
        pay_period (str): The pay period end date in MM/DD/YYYY format.
        user (dict): The authenticated user object containing an 'email' key.

    Returns:
        list[Employee]: Employee objects visible to the current user for the specified pay period.
    """
    parts = pay_period.split("/")
    period = f"{parts[2]}{parts[0]}{parts[1]}"
    df = run_query(conn, "SELECT * FROM dbo.fn_GetEmployeesByManagerEmail(?, ?);", [user['email'], period])
    return [Employee(
        row["EmployeeCode"],
        row["EmployeeLast"],
        row["EmployeeFirst"],
        row["DepartmentCode"],
        row["WorkEmail"],
        None,
        row["PayPeriodHours"]
    ) for _, row in df.iterrows()]


def getRecords(conn, schedule_id):
    """
    Retrieves all allocation records associated with a given Schedule entry.

    These records represent the Task, Fund, and Hours breakdown that employees
    or managers fill in against each scheduled day.

    Args:
        conn (pyodbc.Connection): An active database connection.
        schedule_id (str): The ScheduleID to fetch records for.

    Returns:
        pd.DataFrame | None: A DataFrame with columns Task, Fund, Hours, and ID,
                             or None if no records exist.
    """
    return run_query(conn, """
        SELECT Task, Fund, Hours, ID
        FROM dbo.Record
        WHERE ScheduleID = ?
    """, [schedule_id])


def getTasks(conn):
    """
    Retrieves all available activity codes and descriptions from the Activities table.

    Returns each entry as a 'Code:Description' string, which is the format expected
    by the Task selectbox column in the allocation data editor.

    Args:
        conn (pyodbc.Connection): An active database connection.

    Returns:
        list[str]: Activity options in 'Code:Description' format.
    """
    df = run_query(conn, "SELECT Code, Description FROM dbo.[Activities]")
    return (df["Code"] + ":" + df["Description"]).tolist()


def getFundAllocations(conn, work_email):
    df = run_query(conn, """
        SELECT FundCode, Percentage
        FROM CRT_INFO.dbo.ADUsers
        WHERE LOWER(WorkEmail) = LOWER(?)
    """, [work_email])
    if df is None or df.empty:
        return []
    return df.to_dict("records")


def getFundsByEmployee(conn, employee_code):
    """
    Retrieves the funds associated with a specific employee.

    Joins EmployeeFundMatch against the Funds table to resolve descriptions and
    returns each fund as a 'FundCode:FundDescription' string for use in the Fund
    selectbox column in the allocation data editor.

    Args:
        conn (pyodbc.Connection): An active database connection.
        employee_code (str): The employee's unique identifier.

    Returns:
        list[str]: Fund options in 'FundCode:FundDescription' format.
    """
    df = run_query(conn, """
        SELECT DISTINCT F.FundCode, F.FundDescription
        FROM Funds AS F
        LEFT JOIN dbo.vw_EmployeeFundCodes AS E ON F.FundCode = E.FundCode
        WHERE E.EmployeeCode = ?
    """, [employee_code])
    return (df["FundCode"] + ":" + df["FundDescription"]).tolist()


def saveAllocations(conn, schedule_id, edited_df):
    """
    Persists allocation rows from the UI data editor to the Record table.

    Rows without an ID are treated as new and receive an INSERT with a generated identifier.
    Rows with an existing ID are updated in place. Rows where Hours is NaN or all columns
    are null are skipped. Returns the DataFrame with any newly generated IDs filled in.

    Args:
        conn (pyodbc.Connection): An active database connection.
        schedule_id (str): The ScheduleID these records belong to.
        edited_df (pd.DataFrame): The edited DataFrame from the Streamlit data editor,
                                  containing ID, Task, Fund, and Hours columns.

    Returns:
        pd.DataFrame: The updated DataFrame with ID values populated for newly inserted rows.
    """
    max_id_df = run_query(conn, "SELECT ISNULL(MAX(ID), 0) AS max_id FROM dbo.Record")
    next_id = int(max_id_df.iloc[0, 0]) + 1
    edited_df = edited_df.dropna(how="all").copy()
    edited_df["Hours"] = pd.to_numeric(edited_df["Hours"], errors="coerce")

    for idx, row in edited_df.iterrows():
        pct = row["Hours"]
        if pd.isna(pct):
            continue

        if pd.isna(row["ID"]) or row["ID"] == "":
            new_id = next_id
            next_id += 1
            edited_df.at[idx, "ID"] = new_id
            run_query(conn, """
                INSERT INTO dbo.Record (Task, Fund, Hours, ID, ScheduleID)
                VALUES (?, ?, ?, ?, ?)
            """, [str(row["Task"]), str(row["Fund"]), float(pct), int(new_id), str(schedule_id)])
        else:
            run_query(conn, """
                UPDATE dbo.Record
                SET Task = ?, Fund = ?, Hours = ?, ScheduleID = ?
                WHERE ID = ?
            """, [str(row["Task"]), str(row["Fund"]), float(pct), str(schedule_id), int(row["ID"])])

    return edited_df


def deleteRecord(conn, recordID):
    """
    Deletes a Record entry from the database by its ID.

    Uses a LIKE pattern match to accommodate how IDs may be formatted when passed in.

    Args:
        conn (pyodbc.Connection): An active database connection.
        recordID (int): The ID of the record to delete.

    Returns:
        None
    """
    run_query(conn, "DELETE FROM Record WHERE ID = ?", [recordID])


def changeTimecardState(emplyeeCode, approverCode, payPeriod, conn, approval, acknowledged):
    """
    Updates the approval and acknowledgement state of a Time_Card record.

    Called whenever either the Manager Approval or Employee Acknowledgement checkbox is toggled
    in the UI. Stamps today's date on both ApprovedDate and AcknowledgedDate at the time of the
    update. This function is only invoked when a value has actually changed, so no additional
    change detection is needed here.

    Args:
        emplyeeCode (str): The employee code whose Time_Card is being updated.
        approverCode (str): The employee code of the user performing the action.
        payPeriod (str): The pay period end date in MM/DD/YYYY format.
        conn (pyodbc.Connection): An active database connection.
        approval (bool | int): The new approval state.
        acknowledged (bool | int): The new acknowledgement state.

    Returns:
        None
    """
    parts = payPeriod.split("/")
    period = f"{parts[2]}{parts[0]}{parts[1]}"
    timeCardID = f'TCARD{emplyeeCode}{period}'
    today = datetime.today().strftime('%Y-%m-%d')

    current = run_query(conn, "SELECT Approval, Acknowledged FROM Time_Card WHERE TimeCardID = ?", [timeCardID])
    prev_approval     = int(current.iloc[0, 0]) if current is not None and not current.empty and pd.notna(current.iloc[0, 0]) else 0
    prev_acknowledged = int(current.iloc[0, 1]) if current is not None and not current.empty and pd.notna(current.iloc[0, 1]) else 0

    new_approved_date     = today if int(approval)     != prev_approval     else None
    new_acknowledged_date = today if int(acknowledged) != prev_acknowledged else None

    run_query(conn, """
        UPDATE Time_Card
        SET Approval        = ?,
            ApprovedBy      = CASE WHEN ? IS NOT NULL THEN ? ELSE ApprovedBy END,
            ApprovedDate    = CASE WHEN ? IS NOT NULL THEN ? ELSE ApprovedDate END,
            Acknowledged    = ?,
            AcknowledgedDate = CASE WHEN ? IS NOT NULL THEN ? ELSE AcknowledgedDate END
        WHERE TimeCardID = ?
    """, [approval, new_approved_date, approverCode, new_approved_date, new_approved_date,
          acknowledged, new_acknowledged_date, new_acknowledged_date, timeCardID])


def checkState(employeeCode, payPeriod, conn):
    """
    Retrieves the current approval and acknowledgement state for an employee's Time_Card.

    Returns (0, 0) if no Time_Card exists for the given employee and pay period,
    ensuring the UI checkboxes initialize to unchecked by default.

    Args:
        employeeCode (str): The employee's unique identifier.
        payPeriod (str): The pay period end date in MM/DD/YYYY format.
        conn (pyodbc.Connection): An active database connection.

    Returns:
        tuple[int, int]: A tuple of (approval, acknowledged), each 0 or 1.
    """
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

    approval = int(df.iloc[0, 0]) if pd.notna(df.iloc[0, 0]) else 0
    acknowledged = int(df.iloc[0, 1]) if pd.notna(df.iloc[0, 1]) else 0
    return (approval, acknowledged)
