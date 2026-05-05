from Controllers.DB import run_query

def logImport(conn, imported_by, pay_period, pay_period_start, records_added, skipped_existing, missing_employees):
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
    return run_query(conn, "SELECT * FROM dbo.ImportHistory ORDER BY ImportedAt DESC")
