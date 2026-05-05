import pandas as pd
import pyodbc
from Classes.Employee import *


def get_connection():
    return pyodbc.connect(
        'DRIVER={ODBC Driver 17 for SQL Server};SERVER=CRT-SQL;DATABASE=PARS;Trusted_Connection=yes;'
    )


def load_table(table_name):
    conn = get_connection()
    query = f"SELECT * FROM [{table_name}]"
    df = pd.read_sql(query, conn)
    conn.close()
    return df


def run_query(conn, query, params=None):
    try:
        cursor = conn.cursor()
        cursor.execute(query, params or [])

        if cursor.description is not None:
            columns = [col[0] for col in cursor.description]
            rows = cursor.fetchall()
            return pd.DataFrame.from_records(rows, columns=columns)
        else:
            conn.commit()
            return None

    except Exception as e:
        return None


def setLoggedInUser(conn, user):
    df = run_query(conn, """
     SELECT * FROM dbo.fn_GetEmployee(?);
    """, [user['email']])

    return [Employee(
        row["EmployeeCode"],
        row["EmployeeLast"],
        row["EmployeeFirst"],
        row["DepartmentCode"],
        row["WorkEmail"],
        row["ManagingDepartment"],
        row["PayPeriodHours"]
    ) for _, row in df.iterrows()]
