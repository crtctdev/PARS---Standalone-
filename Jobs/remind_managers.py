import os
import toml
import requests
import pyodbc
import msal
import pandas as pd
from datetime import datetime

#Run Once A week 


try:
    _secrets_path = os.path.join(os.path.dirname(__file__), "..", ".streamlit", "secrets.toml")
    _s            = toml.load(_secrets_path)
    CLIENT_ID     = _s["AZURE_CLIENT_ID"]
    CLIENT_SECRET = _s["AZURE_CLIENT_SECRET"]
    TENANT_ID     = _s["AZURE_TENANT_ID"]
except (FileNotFoundError, KeyError):
    CLIENT_ID     = os.environ.get("AZURE_CLIENT_ID", "")
    CLIENT_SECRET = os.environ.get("AZURE_CLIENT_SECRET", "")
    TENANT_ID     = os.environ.get("AZURE_TENANT_ID", "")
SENDER_EMAIL  = "automation@crtct.org"
PARS_URL      = "https://apps.crtct.org:8056/"

GRAPH_SCOPES  = ["https://graph.microsoft.com/.default"]
AUTHORITY     = f"https://login.microsoftonline.com/{TENANT_ID}"


def get_graph_token():
    app = msal.ConfidentialClientApplication(CLIENT_ID, authority=AUTHORITY, client_credential=CLIENT_SECRET)
    result = app.acquire_token_for_client(scopes=GRAPH_SCOPES)
    if "access_token" not in result:
        raise RuntimeError(f"Failed to acquire Graph token: {result.get('error_description')}")
    return result["access_token"]


def get_unapproved(conn):
    cursor = conn.cursor()
    cursor.execute("""
        With UnApprovedManagers As (
            Select Distinct ManagerWorkEmail
            From dbo.fn_GetTimeCards()
            Where Acknowledged = 1
            And (Approval <> 1 Or Approval Is Null)
        )
        Select
            M.ManagerWorkEmail,
            T.WorkEmail    As EmployeeEmail,
            T.PayPeriod,
            T.Approval,
            T.Acknowledged
        From UnApprovedManagers As M
        Join dbo.fn_GetTimeCards() As T On T.ManagerWorkEmail = M.ManagerWorkEmail
        Where T.Acknowledged = 1
        And (T.Approval <> 1 Or T.Approval Is Null)
        Order By M.ManagerWorkEmail, T.PayPeriod ASC
    """)
    columns = [col[0] for col in cursor.description]
    return pd.DataFrame.from_records(cursor.fetchall(), columns=columns)


def format_pay_period(value):
    try:
        return datetime.strptime(str(value), "%Y%m%d").strftime("%B %d, %Y")
    except Exception:
        return str(value)


def build_email_body(rows):
    rows_html = ""
    for row in rows:
        pay_period = format_pay_period(row["PayPeriod"])
        rows_html += f"""
            <tr>
                <td style="padding:8px; border:1px solid #ddd;">{row['EmployeeEmail']}</td>
                <td style="padding:8px; border:1px solid #ddd;">{pay_period}</td>
            </tr>
        """

    return f"""
        <p>Hello,</p>
        <p>The following employees have acknowledged their timecards but are still <strong>pending your approval</strong>. Please log in to PARS and approve them as soon as possible.</p>

        <table style="border-collapse:collapse; width:100%; font-family:Arial, sans-serif; font-size:14px;">
            <thead>
                <tr style="background-color:#4472C4; color:white;">
                    <th style="padding:8px; border:1px solid #ddd; text-align:left;">Employee</th>
                    <th style="padding:8px; border:1px solid #ddd; text-align:left;">Pay Period</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>

        <br>
        <p>
            <a href="{PARS_URL}" style="background-color:#4472C4; color:white; padding:10px 20px; text-decoration:none; border-radius:4px;">
                Go to PARS
            </a>
        </p>
        <br>
        <p style="color:#888; font-size:12px;">If you believe this is an error, please contact HR.</p>
    """


def send_email(token, to_address, rows):
    url = f"https://graph.microsoft.com/v1.0/users/{SENDER_EMAIL}/sendMail"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    body = {
        "message": {
            "subject": "Action Required: Timecards Pending Your Approval in PARS",
            "body": {
                "contentType": "HTML",
                "content": build_email_body(rows)
            },
            "toRecipients": [{"emailAddress": {"address": to_address}}]
        }
    }

    response = requests.post(url, headers=headers, json=body)
    return response.status_code == 202


def main():
    conn = pyodbc.connect(
        "DRIVER={ODBC Driver 17 for SQL Server};SERVER=CRT-SQL;DATABASE=PARS;Trusted_Connection=yes;"
    )

    df = get_unapproved(conn)
    conn.close()

    if df.empty:
        print("No unapproved timecards found.")
        return

    token = get_graph_token()
    sent = 0
    failed = 0

    for manager_email, group in df.groupby("ManagerWorkEmail"):
        rows = group.to_dict("records")
        success = send_email(token, manager_email, rows)
        status = "SENT" if success else "FAILED"
        print(f"[{status}] {manager_email}  ({len(rows)} employee(s))")

        if success:
            sent += 1
        else:
            failed += 1

    print(f"\nDone. Sent: {sent}  Failed: {failed}")


if __name__ == "__main__":
    main()
