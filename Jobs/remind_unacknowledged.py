import os
import toml
import requests
import pyodbc
import msal
import pandas as pd
from datetime import datetime

TEST_EMAIL   = "mapheyp@crtct.org"

_secrets_path = os.path.join(os.path.dirname(__file__), "..", ".streamlit", "secrets.toml")
_secrets      = toml.load(_secrets_path)

CLIENT_ID     = _secrets["AZURE_CLIENT_ID"]
CLIENT_SECRET = _secrets["AZURE_CLIENT_SECRET"]
TENANT_ID     = _secrets["AZURE_TENANT_ID"]
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


def get_unacknowledged(conn):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT *
        FROM dbo.fn_GetTimeCards()
        WHERE (Acknowledged <> 1 OR Acknowledged IS NULL)
        AND WorkEmail = ?
        Order By PayPeriod ASC
    """, TEST_EMAIL)
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
        pay_period  = format_pay_period(row["PayPeriod"])
        approved    = "Yes" if row["Approval"] else "No"
        rows_html += f"""
            <tr>
                <td style="padding:8px; border:1px solid #ddd;">{pay_period}</td>
                <td style="padding:8px; border:1px solid #ddd;">{approved}</td>
            </tr>
        """

    return f"""
        <p>Hello,</p>
        <p>The following timecards have <strong>not been acknowledged</strong>. Please log in to PARS and acknowledge them as soon as possible.</p>

        <table style="border-collapse:collapse; width:100%; font-family:Arial, sans-serif; font-size:14px;">
            <thead>
                <tr style="background-color:#4472C4; color:white;">
                    <th style="padding:8px; border:1px solid #ddd; text-align:left;">Pay Period</th>
                    <th style="padding:8px; border:1px solid #ddd; text-align:left;">Approved</th>
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
        <p style="color:#888; font-size:12px;">If you believe this is an error, please contact your manager.</p>
    """


def send_email(token, to_address, rows):
    url = f"https://graph.microsoft.com/v1.0/users/{SENDER_EMAIL}/sendMail"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    body = {
        "message": {
            "subject": "Action Required: Unacknowledged Timecards in PARS",
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

    df = get_unacknowledged(conn)
    conn.close()

    if df.empty:
        print("No unacknowledged timecards found.")
        return

    token = get_graph_token()
    sent = 0
    failed = 0

    for email, group in df.groupby("WorkEmail"):
        rows = group.to_dict("records")
        success = send_email(token, email, rows)
        status = "SENT" if success else "FAILED"
        print(f"[{status}] {email}  ({len(rows)} timecard(s))")

        if success:
            sent += 1
        else:
            failed += 1

    print(f"\nDone. Sent: {sent}  Failed: {failed}")


if __name__ == "__main__":
    main()
