from Controllers.DB import run_query


def logImport(conn, imported_by, pay_period, pay_period_start, records_added, skipped_existing, missing_employees):
    """
    Writes an audit entry to the ImportHistory table following a timecard upload.

    Records the importing user's email, the pay period boundaries, how many records
    were successfully added versus skipped due to duplicates, and any employee codes
    that could not be matched in the system. Missing employees are stored as a
    comma-separated string; None is used when all employees were resolved.

    Args:
        conn (pyodbc.Connection): An active database connection.
        imported_by (str): The email address of the user who performed the import.
        pay_period (str): The pay period end date in YYYYMMDD format.
        pay_period_start (str): The pay period start date in YYYYMMDD format.
        records_added (int): The number of Schedule records successfully inserted.
        skipped_existing (int): The number of records skipped due to prior existence.
        missing_employees (list[str]): Employee codes not found in EmployeeInformation.

    Returns:
        None
    """
    run_query(conn, """
        INSERT INTO dbo.ImportHistory
            (ImportedBy, PayPeriod, PayPeriodStart, RecordsAdded, SkippedExisting, MissingEmployees)
        VALUES (?, ?, ?, ?, ?, ?)
    """, [
        imported_by,
        pay_period,
        pay_period_start,
        records_added,
        skipped_existing,
        ','.join(missing_employees) if missing_employees else None
    ])


def getImportHistory(conn):
    """
    Retrieves the full import history log, ordered by most recent first.

    Args:
        conn (pyodbc.Connection): An active database connection.

    Returns:
        pd.DataFrame: All rows from ImportHistory ordered by ImportedAt descending.
    """
    return run_query(conn, "SELECT * FROM dbo.ImportHistory ORDER BY ImportedAt DESC")
