import pandas as pd
import pyodbc
from datetime import datetime
from Classes.Employee import *

# --------------------------
# Database connection
# --------------------------
def get_connection():
    return pyodbc.connect(
        'DRIVER={ODBC Driver 17 for SQL Server};SERVER=CRT-SQL;DATABASE=PARS;Trusted_Connection=yes;'
    )

# --------------------------
# Helper functions
# --------------------------
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
        
        # Only fetch results if it's a SELECT query
        if cursor.description is not None:
            columns = [col[0] for col in cursor.description]
            rows = cursor.fetchall()
            return pd.DataFrame.from_records(rows, columns=columns)
        else:
            conn.commit()  # commit for INSERT/UPDATE/DELETE
            return None
            
    except Exception as e:
        
        return None



def group_df(df, colName):
    groups = df.groupby(colName)
    return groups



def setLoggedInUser(conn, user):
    
    """
    Set Main App Full User 
    """
    df = run_query(conn, """
     SELECT * FROM dbo.fn_GetEmployee(?);
    """, [user['email']]
    )
    
    #never gets more than one 
    return [Employee(
        row["EmployeeCode"],
        row["EmployeeLast"],
        row["EmployeeFirst"],
        row["DepartmentCode"],
        row["WorkEmail"],
        row["ManagingDepartment"],
        row["PayPeriodHours"]
        
        
    ) for _, row in df.iterrows()]