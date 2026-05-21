import pandas as pd
import pyodbc
from Classes.Employee import *


def get_connection():
    """
    Returns a cached pyodbc connection to the PARS database on CRT-SQL
    using Windows Integrated Authentication.

    The connection is cached for the lifetime of the Streamlit session so that
    repeated reruns do not open a new connection each time.

    Returns:
        pyodbc.Connection: An open connection to the PARS database.
    """
    import streamlit as st

    @st.cache_resource
    def _connect():
        return pyodbc.connect(
            'DRIVER={ODBC Driver 17 for SQL Server};SERVER=CRT-SQL;DATABASE=PARS;Trusted_Connection=yes;'
        )

    return _connect()


def load_table(table_name):
    """
    Loads the full contents of a database table into a DataFrame.

    Args:
        table_name (str): The name of the table to query.

    Returns:
        pd.DataFrame: All rows and columns from the specified table.
    """
    conn = get_connection()
    query = f"SELECT * FROM [{table_name}]"
    df = pd.read_sql(query, conn)
    conn.close()
    return df


def run_query(conn, query, params=None):
    """
    Executes a parameterized SQL query against the provided connection.

    For SELECT statements, fetches all rows and returns them as a DataFrame.
    For INSERT, UPDATE, DELETE, and EXEC statements, commits the transaction
    and returns None. Returns None silently on any exception to prevent
    application crashes — callers should check the result before using it.

    Args:
        conn (pyodbc.Connection): An active database connection.
        query (str): The SQL query to execute.
        params (list, optional): A list of parameter values for the query placeholders.

    Returns:
        pd.DataFrame | None: A DataFrame for SELECT queries, None for all others or on error.
    """
    try:
        cursor = conn.cursor()
        cursor.execute(query, params or [])

        if cursor.description is not None:
            columns = [col[0] for col in cursor.description]
            rows = cursor.fetchall()
            result = pd.DataFrame.from_records(rows, columns=columns)
        else:
            conn.commit()
            result = None

        cursor.close()
        return result

    except Exception as e:
        print(f"[run_query] ERROR: {e}\nQuery: {query}\nParams: {params}")
        return None


def setLoggedInUser(conn, user):
    """
    Resolves the Azure AD login user to an Employee record in the PARS database.

    Queries fn_GetEmployee using the user's email address and constructs a list
    of Employee objects from the result. In practice this list will contain exactly
    one entry per valid user. An empty list indicates the email is not registered
    in the system, which the application uses to deny access.

    Args:
        conn (pyodbc.Connection): An active database connection.
        user (dict): The authenticated user object containing at minimum an 'email' key.

    Returns:
        list[Employee]: A list of Employee objects matching the provided email.
    """
    df = run_query(conn, """
     SELECT * FROM dbo.fn_GetEmployee(?);
    """, [user['email']])

    if df is None or df.empty:
        return []

    return [Employee(
        row["EmployeeCode"],
        row["EmployeeLast"],
        row["EmployeeFirst"],
        row["DepartmentCode"],
        row["WorkEmail"],
        row["ManagingDepartment"],
        row["PayPeriodHours"]
    ) for _, row in df.iterrows()]
